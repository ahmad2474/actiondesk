"""Real PostgreSQL workflows and constraint enforcement; no external effects."""

import pytest
from sqlalchemy import Engine

from tests.workflow_cases import WorkflowCases
from tests.workflow_support import World, build_world

pytestmark = pytest.mark.integration


@pytest.fixture
def world(database: Engine) -> World:
    return build_world(database)


class TestWorkflows(WorkflowCases):
    pass


def test_concurrent_approval_and_exact_retry(world: World) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4

    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app.db.models import ApprovalDecision, RequestEvent
    from app.domain.errors import DomainError

    record = world.submit()
    gate = Barrier(2)

    def decide() -> int:
        gate.wait(timeout=10)
        try:
            world.act(record, world.manager, "approve", approval_id=str(record.approvals[0].id))
            return 200
        except DomainError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(decide) for _ in range(2)]
        assert sorted(future.result(timeout=30) for future in futures) == [200, 409]
    with Session(world.engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalDecision)) == 1
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 4
    another = world.submit()
    retry_key = uuid4()
    gate = Barrier(2)

    def retry() -> object:
        gate.wait(timeout=10)
        return world.act(
            another,
            world.manager,
            "approve",
            key=retry_key,
            approval_id=str(another.approvals[0].id),
        ).outcome

    with ThreadPoolExecutor(max_workers=2) as executor:
        retry_futures = [executor.submit(retry) for _ in range(2)]
        assert retry_futures[0].result(timeout=30) == retry_futures[1].result(timeout=30)
    with Session(world.engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalDecision)) == 2


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE request_fields SET fields=jsonb_set(fields,'{amount}','\"1.00\"') "
        "WHERE request_id=:id",
        "DELETE FROM request_fields WHERE request_id=:id",
        "UPDATE requests SET raw_text='Modified confidential description' WHERE id=:id",
        "UPDATE requests SET created_by=:different WHERE id=:id",
        "UPDATE requests SET approval_policy_id=NULL WHERE id=:id",
        "UPDATE approvals SET status='approved',decided_at=now(),decision_reason='Forged' "
        "WHERE request_id=:id",
        "UPDATE approvals SET approver_id=:actor WHERE request_id=:id",
        "DELETE FROM approvals WHERE request_id=:id",
        "UPDATE approval_candidates SET routing_source='department_manager' WHERE request_id=:id",
        "DELETE FROM approval_candidates WHERE request_id=:id",
        "UPDATE approval_policies SET definition='{}' WHERE id=:policy",
        "UPDATE requests SET workflow_version=NULL WHERE id=:id",
        "UPDATE requests SET status='COMPLETED',version=version+1,processed_by=:actor,"
        "processing_role='finance',completed_at=now() WHERE id=:id",
    ],
)
def test_direct_sql_cannot_bypass_submission_or_evidence(world: World, mutation: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    record = world.submit(amount="100.01")
    with pytest.raises(IntegrityError), world.engine.begin() as connection:
        connection.execute(
            text(mutation),
            {
                "id": record.id,
                "actor": world.owner.user_id,
                "different": world.manager.user_id,
                "policy": record.approval_policy_id,
            },
        )


@pytest.mark.parametrize("table", ["approval_decisions", "request_events", "mutation_receipts"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_durable_decisions_history_receipts_are_immutable(
    world: World, table: str, operation: str
) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    record = world.submit()
    record = world.act(
        record, world.manager, "approve", approval_id=str(record.approvals[0].id)
    ).request
    sql = (
        f"DELETE FROM {table} WHERE request_id=:id"
        if operation == "DELETE"
        else (f"UPDATE {table} SET request_id=request_id WHERE request_id=:id")
    )
    with pytest.raises(DBAPIError), world.engine.begin() as connection:
        connection.execute(text(sql), {"id": record.id})


def test_completion_attribution_cannot_be_cleared(world: World) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    record = world.submit()
    record = world.act(
        record, world.manager, "approve", approval_id=str(record.approvals[0].id)
    ).request
    record = world.act(record, world.finance, "process", reference="Synthetic").request
    for clause in (
        "processed_by=NULL,processing_role=NULL",
        "completed_at=NULL",
        "approved_at=NULL",
        "processing_reference='Changed'",
        "status='DRAFT',version=version+1",
    ):
        with pytest.raises(IntegrityError), world.engine.begin() as connection:
            connection.execute(
                text(f"UPDATE requests SET {clause} WHERE id=:id"), {"id": record.id}
            )


def test_legacy_fixture_plans_remain_unvalidated(
    database: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import select, text
    from sqlalchemy.orm import Session

    from app.db.models import Request
    from app.db.seed import fixture_id, seed
    from app.domain.errors import DomainError
    from app.domain.identity import Principal
    from app.services.legacy_plans import assess_legacy_plan
    from app.services.requests import get_request

    configuration = Config("alembic.ini")
    command.downgrade(configuration, "0003_auth_sessions")
    seed(
        database, 100
    )  # Model seed inserts only original columns, preserving historical provenance.
    with database.connect() as connection:
        history = connection.execute(
            text("SELECT to_jsonb(e)::text FROM request_events e ORDER BY id")
        ).all()
        approvals = connection.execute(
            text("SELECT id,approver_id,status,decided_at FROM approvals ORDER BY id")
        ).all()
    command.upgrade(configuration, "head")
    seed(database, 100)
    owner = Principal(fixture_id("organization"), fixture_id("user/employee"))
    with database.begin() as connection:
        connection.execute(text("UPDATE users SET status='active'"))
    with Session(database) as session:
        record = session.scalar(select(Request).where(Request.type == "expense"))
        assert record is not None
        detail = get_request(session, owner, record.id)
        assessment = assess_legacy_plan(session, record)
        assert "Step 1 has no historical candidate snapshot" in assessment.blockers
        assert (
            "Historical policy does not establish the approved complete plan" in assessment.blockers
        )
    with pytest.raises(DomainError) as error:
        World(database, owner, fixture_id("department"), owner, owner, owner, owner, owner).act(
            detail, owner, "cancel"
        )
    assert error.value.status == 409 and "Legacy" in error.value.detail
    import json

    from app.core.validate_legacy_approvals import main as assess_main

    monkeypatch.setattr(
        "sys.argv", ["validate-legacy", "--organization-id", str(owner.organization_id)]
    )
    capsys.readouterr()
    with pytest.raises(SystemExit) as exit_result:
        assess_main()
    assert exit_result.value.code == 1
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert reports and all(set(report) == {"request_id", "blockers"} for report in reports)
    with database.connect() as connection:
        assert (
            connection.execute(
                text("SELECT to_jsonb(e)::text FROM request_events e ORDER BY id")
            ).all()
            == history
        )
        assert (
            connection.execute(
                text("SELECT id,approver_id,status,decided_at FROM approvals ORDER BY id")
            ).all()
            == approvals
        )
        assert connection.scalar(text("SELECT count(*) FROM approval_decisions")) == 0
        assert connection.scalar(text("SELECT count(*) FROM approval_candidates")) == 0
        assert connection.scalar(text("SELECT count(*) FROM active_approval_policies")) == 0


def test_downgrade_refuses_to_discard_live_evidence(world: World) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.exc import DBAPIError

    world.submit()
    with pytest.raises(DBAPIError, match="downgrade blocked"):
        command.downgrade(Config("alembic.ini"), "0003_auth_sessions")


@pytest.mark.parametrize(
    "kind,target", [("service", "CLOSED"), ("expense", "APPROVED"), ("leave", "COMPLETED")]
)
def test_invalid_edges_fail_even_with_matching_audit_event(
    world: World, kind: str, target: str
) -> None:
    from uuid import uuid4

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    record = world.create(kind)
    with pytest.raises(IntegrityError), world.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO request_events(id,organization_id,request_id,sequence,"
                "actor_id,action,from_state,to_state,reason,at) "
                "VALUES(:event,:org,:id,2,:actor,'close',"
                ":source,:target,'Synthetic invalid edge',now())"
            ),
            {
                "event": uuid4(),
                "org": world.owner.organization_id,
                "id": record.id,
                "actor": world.admin.user_id,
                "source": record.status.value,
                "target": target,
            },
        )
        connection.execute(
            text("UPDATE requests SET status=:target,version=2 WHERE id=:id"),
            {"id": record.id, "target": target},
        )


def test_decision_cannot_be_appended_without_a_state_change(world: World) -> None:
    from uuid import uuid4

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    record = world.submit()
    with pytest.raises(IntegrityError), world.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO request_events(id,organization_id,request_id,sequence,"
                "actor_id,action,from_state,to_state,reason,at) "
                "VALUES(:event,:org,:id,100,:actor,'approve',"
                "'MANAGER_REVIEW','APPROVED','Synthetic forgery',now())"
            ),
            {
                "event": uuid4(),
                "org": world.owner.organization_id,
                "id": record.id,
                "actor": world.manager.user_id,
            },
        )
        connection.execute(
            text(
                "INSERT INTO approval_decisions(id,organization_id,approval_id,request_id,"
                "requester_id,actor_id,required_role,outcome,reason,at,event_sequence) "
                "VALUES(:decision,:org,"
                ":approval,:id,:owner,:actor,'manager','approved','Synthetic forgery',now(),100)"
            ),
            {
                "decision": uuid4(),
                "org": world.owner.organization_id,
                "approval": record.approvals[0].id,
                "id": record.id,
                "owner": world.owner.user_id,
                "actor": world.manager.user_id,
            },
        )
