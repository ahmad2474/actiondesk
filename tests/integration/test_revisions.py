"""Live transaction, constraint, migration and concurrency revision tests."""

from uuid import UUID

import pytest
from sqlalchemy import Engine

from tests.revision_cases import RevisionCases
from tests.workflow_support import World, build_world

pytestmark = pytest.mark.integration


@pytest.fixture
def world(database: Engine) -> World:
    return build_world(database)


class TestRevisions(RevisionCases):
    pass


@pytest.mark.parametrize("action", ["request_changes", "revise", "resubmit"])
@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_revision_mutations(world: World, action: str, same_key: bool) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4

    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app.db.models import RequestChangeRequest, RequestRevision, RequestSubmission
    from app.domain.errors import DomainError
    from tests.revision_cases import changes, propose
    from tests.workflow_support import submission

    record = world.submit() if action == "request_changes" else changes(world)
    if action == "resubmit":
        record = propose(world, record)
    extra: dict[str, object]
    actor = world.manager if action == "request_changes" else world.owner
    if action == "request_changes":
        extra = {"approval_id": str(record.approvals[0].id)}
    elif action == "revise":
        extra = {"data": submission(), "clarification": "Concurrent correction"}
    else:
        assert record.proposed_revision
        extra = {"revision_id": str(record.proposed_revision.id)}
    gate = Barrier(2)
    key = uuid4()

    def execute() -> int:
        gate.wait(timeout=10)
        try:
            world.act(record, actor, action, key=key if same_key else uuid4(), **extra)
            return 200
        except DomainError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(execute) for _ in range(2)]
        assert sorted(future.result(timeout=30) for future in futures) == (
            [200, 200] if same_key else [200, 409]
        )
    with Session(world.engine) as session:
        assert session.scalar(select(func.count()).select_from(RequestChangeRequest)) == 1
        assert session.scalar(select(func.count()).select_from(RequestSubmission)) == (
            2 if action == "resubmit" else 1
        )
        assert session.scalar(select(func.count()).select_from(RequestRevision)) == (
            1 if action == "request_changes" else 2
        )


@pytest.mark.parametrize("race", ["approve_changes", "revise_resubmit", "cancel_resubmit"])
def test_competing_revision_actions(world: World, race: str) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.domain.errors import DomainError
    from app.domain.identity import Principal
    from tests.revision_cases import changes, propose
    from tests.workflow_support import submission

    actions: list[tuple[Principal, str, dict[str, object]]]
    record = world.submit() if race == "approve_changes" else propose(world, changes(world))
    if race == "approve_changes":
        actions = [
            (world.manager, action, {"approval_id": str(record.approvals[0].id)})
            for action in ("approve", "request_changes")
        ]
    else:
        assert record.proposed_revision
        actions = [
            (world.owner, "resubmit", {"revision_id": str(record.proposed_revision.id)}),
            (world.owner, "revise", {"data": submission(), "clarification": "A newer proposal"})
            if race == "revise_resubmit"
            else (world.owner, "cancel", {}),
        ]
    gate = Barrier(2)

    def execute(index: int) -> int:
        actor, action, extra = actions[index]
        gate.wait(timeout=10)
        try:
            world.act(record, actor, action, key=None, **extra)
            return 200
        except DomainError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(execute, index) for index in range(2)]
        assert sorted(future.result(timeout=30) for future in futures) == [200, 409]


@pytest.mark.parametrize(
    "table", ["request_revisions", "request_submissions", "request_change_requests"]
)
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_revision_evidence_immutable(world: World, table: str, operation: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from tests.revision_cases import changes, propose, resubmit

    record = resubmit(world, propose(world, changes(world)))
    sql = (
        f"DELETE FROM {table} WHERE request_id=:id"
        if operation == "DELETE"
        else f"UPDATE {table} SET request_id=request_id WHERE request_id=:id"
    )
    with pytest.raises(DBAPIError), world.engine.begin() as connection:
        connection.execute(text(sql), {"id": record.id})


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE request_fields SET fields=jsonb_set(fields,'{amount}','\"1.00\"') "
        "WHERE request_id=:id",
        "UPDATE requests SET raw_text='New intake' WHERE id=:id",
        "UPDATE requests SET current_submission_sequence=submission_sequence WHERE id=:id",
        "UPDATE requests SET proposed_revision_id=:revision WHERE id=:id",
        "UPDATE requests SET status='APPROVED',version=version+1 WHERE id=:id",
        "UPDATE approvals SET status='pending',closed_event_sequence=NULL WHERE id=:approval",
        "UPDATE approvals SET submission_sequence=:sequence WHERE id=:approval",
        "UPDATE requests SET workflow_version=NULL WHERE id=:id",
    ],
)
def test_current_submission_cannot_be_bypassed(world: World, mutation: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from tests.revision_cases import changes, propose, resubmit

    record = changes(world, finance=True)
    old_approval = record.approvals[0].id
    proposed = propose(world, record)
    assert proposed.proposed_revision
    current = resubmit(world, proposed)
    with pytest.raises(DBAPIError), world.engine.begin() as connection:
        connection.execute(
            text(mutation),
            {
                "id": current.id,
                "revision": proposed.proposed_revision.id,
                "approval": old_approval,
                "sequence": current.current_submission_sequence,
            },
        )


def test_needs_info_is_not_an_unrestricted_edit_window(world: World) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from tests.revision_cases import changes

    record = changes(world)
    with pytest.raises(DBAPIError), world.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE request_fields SET fields=jsonb_set(fields,'{amount}','\"1.00\"') "
                "WHERE request_id=:id"
            ),
            {"id": record.id},
        )
    with pytest.raises(DBAPIError), world.engine.begin() as connection:
        connection.execute(
            text("UPDATE requests SET version=version+1 WHERE id=:id"), {"id": record.id}
        )


def test_missing_revision_event_rolls_back_everything(world: World) -> None:
    from sqlalchemy import event, func, select
    from sqlalchemy.orm import Session

    from app.db.models import RequestEvent, RequestRevision
    from app.services.requests import get_request
    from tests.revision_cases import changes, propose

    record = changes(world)

    def fail(session: Session, context: object, instances: object) -> None:
        if any(isinstance(item, RequestEvent) and item.action == "revise" for item in session.new):
            raise RuntimeError("Injected revision event failure")

    event.listen(Session, "before_flush", fail)
    try:
        with pytest.raises(RuntimeError):
            propose(world, record)
    finally:
        event.remove(Session, "before_flush", fail)
    with Session(world.engine) as session:
        assert get_request(session, world.owner, record.id) == record
        assert session.scalar(select(func.count()).select_from(RequestRevision)) == 1


def original_managed_submission(world: World) -> UUID:
    """Create an actual 0004 managed submission before upgrading; no revision history exists."""
    from uuid import uuid4

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    configuration = Config("alembic.ini")
    command.downgrade(configuration, "0004_workflows")
    request_id, approval_id = uuid4(), uuid4()
    parameters: dict[str, object] = {
        "id": request_id,
        "approval": approval_id,
        "org": world.owner.organization_id,
        "owner": world.owner.user_id,
        "manager": world.manager.user_id,
        "department": world.department,
    }
    with world.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO requests(id,organization_id,type,title,raw_text,statu"
                "s,created_by,department_id,version,workflow_version) VALUES(:id,:"
                "org,'expense','Original','Original intake','DRAFT',:owner,:depart"
                "ment,1,1)"
            ),
            parameters,
        )
        parameters["event"] = uuid4()
        connection.execute(
            text(
                "INSERT INTO request_events(id,organization_id,request_id,sequence"
                ",actor_id,action,from_state,to_state,reason,at) VALUES(:event,:or"
                "g,:id,1,:owner,'created',NULL,'DRAFT','Original creation',now())"
            ),
            parameters,
        )
        connection.execute(
            text(
                "UPDATE requests SET approval_policy_id=(SELECT policy_id FROM act"
                "ive_approval_policies WHERE organization_id=:org AND request_type"
                "='expense'),submission_sequence=2 WHERE id=:id"
            ),
            parameters,
        )
        connection.execute(
            text(
                "INSERT INTO request_fields(organization_id,request_id,schema_vers"
                'ion,fields) VALUES(:org,:id,1,\'{"type":"expense","vendor":"Origin'
                'al vendor","amount":"100.00","currency":"PKR","purpose":"Original'
                " purpose\"}')"
            ),
            parameters,
        )
        connection.execute(
            text(
                "INSERT INTO approvals(id,organization_id,request_id,requester_id,"
                "step,approver_role,status) VALUES(:approval,:org,:id,:owner,1,'ma"
                "nager','pending')"
            ),
            parameters,
        )
        connection.execute(
            text(
                "INSERT INTO approval_candidates(organization_id,approval_id,user_"
                "id,request_id,requester_id,required_role,routing_source) VALUES(:"
                "org,:approval,:manager,:id,:owner,'manager','employee_manager')"
            ),
            parameters,
        )
        for sequence, source, target, action in [
            (2, "DRAFT", "SUBMITTED", "submit"),
            (3, "SUBMITTED", "MANAGER_REVIEW", "route"),
        ]:
            parameters.update(
                event=uuid4(), sequence=sequence, source=source, target=target, action=action
            )
            connection.execute(
                text("UPDATE requests SET status=:target,version=:sequence WHERE id=:id"),
                parameters,
            )
            connection.execute(
                text(
                    "INSERT INTO request_events(id,organization_id,request_id,sequence"
                    ",actor_id,action,from_state,to_state,reason,at) VALUES(:event,:or"
                    "g,:id,:sequence,:owner,:action,:source,:target,'Original submissi"
                    "on',now())"
                ),
                parameters,
            )
    return request_id


@pytest.mark.parametrize("corrupt", [False, True])
def test_milestone3_lazy_capture_requires_real_evidence(world: World, corrupt: bool) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import func, select, text
    from sqlalchemy.orm import Session

    from app.db.models import RequestRevision, RequestSubmission
    from app.domain.errors import DomainError
    from app.services.requests import get_request
    from tests.revision_cases import propose, resubmit

    request_id = original_managed_submission(world)
    if corrupt:
        # Disposable pre-upgrade corruption probe: emulate an incomplete historical record.
        with world.engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE request_fields DISABLE TRIGGER frozen_request_fields")
            )
            connection.execute(
                text("UPDATE request_fields SET schema_version=2 WHERE request_id=:id"),
                {"id": request_id},
            )
            connection.execute(
                text("ALTER TABLE request_fields ENABLE TRIGGER frozen_request_fields")
            )
    with world.engine.connect() as connection:
        before = connection.execute(
            text(
                "SELECT to_jsonb(e)::text FROM request_events e WHERE request_id=:"
                "id ORDER BY sequence"
            ),
            {"id": request_id},
        ).all()
    configuration = Config("alembic.ini")
    command.upgrade(configuration, "head")
    command.check(configuration)
    with Session(world.engine) as session:
        record = get_request(session, world.owner, request_id)
        assert session.scalar(select(func.count()).select_from(RequestRevision)) == 0
    if corrupt:
        with pytest.raises(DomainError) as error:
            world.act(
                record, world.manager, "request_changes", approval_id=str(record.approvals[0].id)
            )
        assert error.value.status == 409
        with Session(world.engine) as session:
            assert get_request(session, world.owner, request_id) == record
            assert session.scalar(select(func.count()).select_from(RequestRevision)) == 0
            assert session.scalar(select(func.count()).select_from(RequestSubmission)) == 0
    else:
        changed = world.act(
            record, world.manager, "request_changes", approval_id=str(record.approvals[0].id)
        ).request
        with Session(world.engine) as session:
            captured = session.scalar(select(RequestRevision))
            assert (
                captured
                and captured.kind == "captured"
                and captured.actor_id == world.manager.user_id
            )
            assert captured.event_sequence == changed.version and captured.at >= record.updated_at
            assert captured.fields == record.structured_fields
        revised = resubmit(world, propose(world, changed))
        assert revised.approvals[0].id != record.approvals[0].id
    with world.engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT to_jsonb(e)::text FROM request_events e WHERE request_id=:"
                    "id AND sequence<=3 ORDER BY sequence"
                ),
                {"id": request_id},
            ).all()
            == before
        )


def test_revision_downgrade_preserves_evidence(world: World) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.exc import DBAPIError

    from tests.revision_cases import changes

    changes(world)
    with pytest.raises(DBAPIError, match="downgrade blocked"):
        command.downgrade(Config("alembic.ini"), "0004_workflows")


def test_revision_http_uses_real_sessions_and_csrf(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    import secrets
    from uuid import uuid4

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.core.auth_config import get_auth_settings
    from app.db.models import User
    from app.main import app
    from app.services.auth import replace_password
    from app.services.login_limits import login_limiter
    from app.services.passwords import password_hasher
    from tests.integration.test_auth_persistence import UnthrottledFixture
    from tests.workflow_support import submission

    origin = "http://127.0.0.1:8000"
    monkeypatch.setenv("ACTIONDESK_AUTH_ORGANIZATION_SLUG", str(world.owner.organization_id))
    get_auth_settings.cache_clear()
    credentials: dict[str, dict[str, str]] = {}
    with Session(world.engine) as session, session.begin():
        for label, actor in (("owner", world.owner), ("manager", world.manager)):
            user = session.get(User, actor.user_id)
            assert user
            password = secrets.token_urlsafe(24)
            replace_password(session, user, password_hasher().hash(password))
            credentials[label] = {"email": user.email, "password": password}
    app.dependency_overrides[login_limiter] = lambda: UnthrottledFixture()
    record = world.submit()
    url = f"/requests/{record.id}/transitions"
    try:
        with TestClient(app, base_url=origin) as client:
            body: dict[str, object] = {
                "action": "request_changes",
                "expected_version": record.version,
                "reason": "Clarify vendor",
                "approval_id": str(record.approvals[0].id),
            }
            assert client.post(url, json=body, headers={"Origin": origin}).status_code == 401
            login = client.post(
                "/auth/login", json=credentials["manager"], headers={"Origin": origin}
            )
            assert login.status_code == 200
            csrf = login.json()["csrf_token"]
            headers = {"Origin": origin, "X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())}
            assert (
                client.post(
                    url, json=body, headers={"Origin": origin, "Idempotency-Key": str(uuid4())}
                ).status_code
                == 403
            )
            response = client.post(url, json=body, headers=headers)
            assert response.status_code == 200, response.text
            changed = response.json()["request"]
            assert changed["correction"]["actor_id"] == str(world.manager.user_id)
            login = client.post(
                "/auth/login", json=credentials["owner"], headers={"Origin": origin}
            )
            assert login.status_code == 200
            headers = {
                "Origin": origin,
                "X-CSRF-Token": login.json()["csrf_token"],
                "Idempotency-Key": str(uuid4()),
            }
            body = {
                "action": "revise",
                "expected_version": changed["version"],
                "reason": "Confirmed",
                "data": submission(),
                "clarification": "Vendor confirmed",
            }
            response = client.post(url, json=body, headers=headers)
            assert response.status_code == 200, response.text
            proposal = response.json()["request"]
            assert proposal["proposed_revision"]["actor_id"] == str(world.owner.user_id)
            body = {
                "action": "resubmit",
                "expected_version": proposal["version"],
                "reason": "Ready",
                "revision_id": proposal["proposed_revision"]["id"],
            }
            headers["Idempotency-Key"] = str(uuid4())
            response = client.post(url, json=body, headers=headers)
            assert response.status_code == 200, response.text
            assert client.get(f"/requests/{record.id}/revisions").status_code == 200
    finally:
        app.dependency_overrides.clear()
        get_auth_settings.cache_clear()


@pytest.mark.parametrize("with_projection", [False, True])
def test_forged_revision_with_history_cannot_bypass_guards(
    world: World, with_projection: bool
) -> None:
    import json
    from uuid import uuid4

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from tests.revision_cases import changes

    record = changes(world)
    with world.engine.connect() as connection:
        predecessor = connection.scalar(
            text("SELECT revision_id FROM request_submissions WHERE request_id=:id"),
            {"id": record.id},
        )
    revision_id = uuid4()
    parameters = {
        "id": record.id,
        "org": world.owner.organization_id,
        "actor": world.owner.user_id,
        "revision": revision_id,
        "predecessor": predecessor,
        "change": record.version,
        "sequence": record.version + 1,
        "event": uuid4(),
        "fields": json.dumps(
            {**(record.structured_fields or {}), **({"bypass": True} if with_projection else {})}
        ),
    }
    with pytest.raises(DBAPIError), world.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO request_events(id,organization_id,request_id,sequence"
                ",actor_id,action,from_state,to_state,reason,at) VALUES(:event,:or"
                "g,:id,:sequence,:actor,'revise','NEEDS_INFO','NEEDS_INFO','Forged"
                " snapshot',now())"
            ),
            parameters,
        )
        # An unbound snapshot or a proposal with fields outside the allowlist must fail at commit.
        connection.execute(
            text(
                "INSERT INTO request_revisions(id,organization_id,request_id,prede"
                "cessor_id,change_sequence,event_sequence,actor_id,at,kind,schema_"
                "version,fields,clarification) VALUES(:revision,:org,:id,:predeces"
                "sor,:change,:sequence,:actor,now(),'proposed',1,CAST(:fields AS j"
                "sonb),'Forged')"
            ),
            parameters,
        )
        if with_projection:
            connection.execute(
                text(
                    "UPDATE requests SET version=:sequence,proposed_revision_id=:revis"
                    "ion WHERE id=:id"
                ),
                parameters,
            )
