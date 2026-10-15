"""Live lifecycle guards, races and migration compatibility."""

import pytest
from sqlalchemy import Engine

from tests.lifecycle_cases import LifecycleCases
from tests.workflow_support import World, build_world

pytestmark = pytest.mark.integration


@pytest.fixture
def world(database: Engine) -> World:
    return build_world(database)


class TestLifecycle(LifecycleCases):
    pass


@pytest.mark.parametrize(
    "action",
    ["request_reversal", "approve_reversal", "reject_reversal", "create_correction", "reopen"],
)
@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_lifecycle_mutations(world: World, action: str, same_key: bool) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4

    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app.db.models import CorrectionLink, ReversalDecision, ReversalRequest, ServiceReopening
    from app.domain.errors import DomainError
    from tests.lifecycle_cases import approved, configure_reopen, held, resolved, reverse

    actor = world.owner
    extra: dict[str, object]
    if action == "request_reversal":
        record = approved(world)
        extra = {"intent": "correct"}
    elif action == "reopen":
        configure_reopen(world)
        record = resolved(world)
        extra = {}
    else:
        record = held(world)
        if action == "create_correction":
            record = reverse(world, record)
        else:
            actor = world.manager
        assert record.active_reversal
        extra = {"reversal_request_id": str(record.active_reversal.id)}
    gate = Barrier(2)
    key = uuid4()

    def run() -> int:
        gate.wait(timeout=10)
        try:
            world.act(record, actor, action, key=key if same_key else uuid4(), **extra)
            return 200
        except DomainError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run) for _ in range(2)]
        assert sorted(future.result(timeout=30) for future in futures) == (
            [200, 200] if same_key else [200, 409]
        )
    with Session(world.engine) as session:
        target = (
            ServiceReopening
            if action == "reopen"
            else CorrectionLink
            if action == "create_correction"
            else ReversalRequest
            if action == "request_reversal"
            else ReversalDecision
        )
        assert session.scalar(select(func.count()).select_from(target)) == 1


@pytest.mark.parametrize("race", ["hold_process", "accept_deny", "reopen_close"])
def test_competing_lifecycle_actions(world: World, race: str) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.domain.errors import DomainError
    from app.domain.identity import Principal
    from tests.lifecycle_cases import approved, configure_reopen, held, resolved

    actions: list[tuple[Principal, str, dict[str, object]]]
    if race == "hold_process":
        record = approved(world)
        actions = [
            (world.owner, "request_reversal", {"intent": "withdraw"}),
            (world.finance, "process", {"reference": "Race"}),
        ]
    elif race == "accept_deny":
        record = held(world)
        assert record.active_reversal
        actions = [
            (world.manager, action, {"reversal_request_id": str(record.active_reversal.id)})
            for action in ("approve_reversal", "reject_reversal")
        ]
    else:
        configure_reopen(world)
        record = resolved(world)
        actions = [(world.owner, "reopen", {}), (world.owner, "close", {})]
    gate = Barrier(2)

    def run(index: int) -> int:
        actor, action, extra = actions[index]
        gate.wait(timeout=10)
        try:
            world.act(record, actor, action, key=None, **extra)
            return 200
        except DomainError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run, index) for index in range(2)]
        results = sorted(future.result(timeout=30) for future in futures)
        assert results == [200, 409]


@pytest.mark.parametrize(
    "table",
    [
        "request_reversal_requests",
        "request_reversal_decisions",
        "request_correction_links",
        "service_resolutions",
        "service_reopenings",
        "service_reopen_policies",
    ],
)
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_lifecycle_evidence_immutable(world: World, table: str, operation: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from tests.lifecycle_cases import configure_reopen, held, resolved, reverse

    record = reverse(world, held(world))
    assert record.active_reversal
    world.act(
        record, world.owner, "create_correction", reversal_request_id=str(record.active_reversal.id)
    )
    configure_reopen(world)
    world.act(resolved(world), world.owner, "reopen")
    clause = "organization_id=organization_id"
    with pytest.raises(DBAPIError), world.engine.begin() as connection:
        connection.execute(
            text(
                f"DELETE FROM {table}" if operation == "DELETE" else f"UPDATE {table} SET {clause}"
            )
        )


@pytest.mark.parametrize("action", ["approve_reversal", "reject_reversal"])
def test_sql_initiator_cannot_decide_with_matching_history(world: World, action: str) -> None:
    from uuid import uuid4

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from tests.lifecycle_cases import approved

    record = world.act(
        approved(world), world.manager, "request_reversal", intent="withdraw"
    ).request
    assert record.active_reversal
    params = {
        "org": world.owner.organization_id,
        "id": record.id,
        "actor": world.manager.user_id,
        "q": record.active_reversal.id,
        "event": uuid4(),
        "decision": uuid4(),
        "version": record.version + 1,
        "action": action,
        "target": "REVERSED" if action == "approve_reversal" else "APPROVED",
        "outcome": "accepted" if action == "approve_reversal" else "denied",
    }
    with pytest.raises(DBAPIError), world.engine.begin() as connection:
        connection.execute(
            text("UPDATE requests SET status=:target,version=:version WHERE id=:id"), params
        )
        connection.execute(
            text(
                "INSERT INTO request_events(id,organization_id,request_id,sequence"
                ",actor_id,action,from_state,to_state,reason,at) VALUES(:event,:or"
                "g,:id,:version,:actor,:action,'REVERSAL_REVIEW',:target,'Forged s"
                "elf review',now())"
            ),
            params,
        )
        connection.execute(
            text(
                "INSERT INTO request_reversal_decisions(id,organization_id,request"
                "_id,reversal_request_id,actor_id,event_sequence,outcome,organizat"
                "ion_timezone) VALUES(:decision,:org,:id,:q,:actor,:version,:outco"
                "me,'UTC')"
            ),
            params,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE requests SET approved_at=NULL WHERE id=:id",
        "UPDATE requests SET status='APPROVED',version=version+1 WHERE id=:id",
        "UPDATE requests SET status='COMPLETED',version=version+1 WHERE id=:id",
        "UPDATE requests SET active_reversal_id=NULL WHERE id=:id",
        "UPDATE requests SET approval_policy_id=NULL WHERE id=:id",
        "UPDATE requests SET current_submission_sequence=NULL WHERE id=:id",
        "UPDATE request_fields SET fields='{}' WHERE request_id=:id",
    ],
)
def test_reversal_sql_bypass_refused(world: World, mutation: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from tests.lifecycle_cases import held

    record = held(world)
    with pytest.raises(DBAPIError), world.engine.begin() as connection:
        connection.execute(text(mutation), {"id": record.id})


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE requests SET resolution='Overwrite first' WHERE id=:id",
        "UPDATE requests SET latest_resolution_id=NULL WHERE id=:id",
        "UPDATE requests SET service_cycle_sequence=4 WHERE id=:id",
        "UPDATE requests SET status='CLOSED',version=version+1 WHERE id=:id",
        "UPDATE requests SET assigned_to=:owner WHERE id=:id",
    ],
)
def test_service_sql_cannot_reuse_old_resolution(world: World, mutation: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from tests.lifecycle_cases import configure_reopen, resolved

    configure_reopen(world)
    record = world.act(resolved(world), world.owner, "reopen").request
    with pytest.raises(DBAPIError), world.engine.begin() as connection:
        connection.execute(text(mutation), {"id": record.id, "owner": world.owner.user_id})


def test_service_expired_policy_cannot_be_bypassed_by_backdated_event(world: World) -> None:
    from uuid import uuid4

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from tests.lifecycle_cases import configure_reopen, resolved

    configure_reopen(world, 3600)
    record = resolved(world)
    assert record.current_resolution
    # A previously valid resolution is aged only in the disposable corruption fixture.
    with world.engine.begin() as connection:
        connection.execute(text("ALTER TABLE request_events DISABLE TRIGGER USER"))
        connection.execute(text("ALTER TABLE service_resolutions DISABLE TRIGGER USER"))
        connection.execute(
            text(
                "UPDATE request_events SET at=at-interval '2 hours' WHERE request_"
                "id=:id AND action='resolve'"
            ),
            {"id": record.id},
        )
        connection.execute(
            text("UPDATE service_resolutions SET at=at-interval '2 hours' WHERE request_id=:id"),
            {"id": record.id},
        )
        connection.execute(text("ALTER TABLE request_events ENABLE TRIGGER USER"))
        connection.execute(text("ALTER TABLE service_resolutions ENABLE TRIGGER USER"))
    from app.domain.errors import DomainError

    with pytest.raises(DomainError) as error:
        world.act(record, world.owner, "reopen")
    assert error.value.status == 409
    with pytest.raises(DBAPIError), world.engine.begin() as connection:
        params = {
            "id": record.id,
            "org": world.owner.organization_id,
            "actor": world.owner.user_id,
            "version": record.version + 1,
            "resolution": record.current_resolution.id,
            "event": uuid4(),
            "reopen": uuid4(),
        }
        connection.execute(
            text(
                "UPDATE requests SET status='REOPENED',version=:version,service_cy"
                "cle_sequence=:version WHERE id=:id"
            ),
            params,
        )
        connection.execute(
            text(
                "INSERT INTO request_events(id,organization_id,request_id,sequence"
                ",actor_id,action,from_state,to_state,reason,at) SELECT :event,:or"
                "g,:id,:version,:actor,'reopen','RESOLVED','REOPENED','Backdated',"
                "at+interval '30 minutes' FROM service_resolutions WHERE id=:resol"
                "ution"
            ),
            params,
        )
        connection.execute(
            text(
                "INSERT INTO service_reopenings(id,organization_id,request_id,reso"
                "lution_id,event_sequence,policy_id,expires_at) SELECT :reopen,:or"
                "g,:id,:resolution,:version,ap.policy_id,sr.at+interval '1 hour' F"
                "ROM service_resolutions sr JOIN active_service_reopen_policies ap"
                " ON ap.organization_id=sr.organization_id WHERE sr.id=:resolution"
            ),
            params,
        )


def test_approved_milestone3_lazy_capture_preserves_real_approval(world: World) -> None:
    from uuid import uuid4

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from app.services.requests import get_request
    from tests.integration.test_revisions import original_managed_submission
    from tests.lifecycle_cases import reverse

    request_id = original_managed_submission(world)
    params = {
        "id": request_id,
        "org": world.owner.organization_id,
        "actor": world.manager.user_id,
        "event": uuid4(),
        "decision": uuid4(),
    }
    with world.engine.begin() as connection:
        connection.execute(
            text("UPDATE requests SET status='APPROVED',version=4,approved_at=now() WHERE id=:id"),
            params,
        )
        connection.execute(
            text(
                "INSERT INTO request_events(id,organization_id,request_id,sequence"
                ",actor_id,action,from_state,to_state,reason,at) VALUES(:event,:or"
                "g,:id,4,:actor,'approve','MANAGER_REVIEW','APPROVED','Real origin"
                "al decision',now())"
            ),
            params,
        )
        connection.execute(
            text(
                "INSERT INTO approval_decisions(id,organization_id,approval_id,req"
                "uest_id,requester_id,actor_id,required_role,outcome,reason,at,eve"
                "nt_sequence) SELECT :decision,:org,a.id,:id,a.requester_id,:actor"
                ",'manager','approved','Real original decision',now(),4 FROM appro"
                "vals a WHERE a.request_id=:id"
            ),
            params,
        )
        connection.execute(
            text(
                "UPDATE approvals SET status='approved',decision_reason='Real orig"
                "inal decision',decided_at=now(),closed_event_sequence=4 WHERE req"
                "uest_id=:id"
            ),
            params,
        )
    with world.engine.connect() as connection:
        before = connection.execute(
            text("SELECT to_jsonb(d)::text FROM approval_decisions d WHERE request_id=:id"), params
        ).all()
    command.upgrade(Config("alembic.ini"), "head")
    command.check(Config("alembic.ini"))
    with Session(world.engine) as session:
        record = get_request(session, world.owner, request_id)
    from app.services.capabilities import get_capabilities

    with Session(world.engine) as session:
        capability = get_capabilities(session, world.owner, request_id)
        assert {entry.action.value for entry in capability.available_actions} == {
            "request_reversal"
        }
    with world.engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM request_submissions")) == 0
        assert connection.scalar(text("SELECT count(*) FROM request_revisions")) == 0
    original = record.approved_at
    record = world.act(record, world.owner, "request_reversal", intent="withdraw").request
    assert reverse(world, record).approved_at == original
    with world.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT to_jsonb(d)::text FROM approval_decisions d WHERE request_id=:id"),
                params,
            ).all()
            == before
        )
        assert (
            connection.scalar(
                text("SELECT kind FROM request_revisions WHERE request_id=:id"), params
            )
            == "approval_capture"
        )


@pytest.mark.parametrize("corrupt", [False, True])
def test_old_managed_service_lazy_capture_requires_trusted_resolution(
    world: World, corrupt: bool
) -> None:
    from uuid import uuid4

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from app.domain.errors import DomainError
    from app.services.requests import get_request
    from tests.lifecycle_cases import configure_reopen

    draft = world.create("service")
    configuration = Config("alembic.ini")
    command.downgrade(configuration, "0005_revisions")
    params: dict[str, object] = {
        "id": draft.id,
        "org": world.owner.organization_id,
        "manager": world.manager.user_id,
        "assignee": world.colleague.user_id,
    }
    with world.engine.begin() as connection:
        for version, source, target, action in [
            (2, "SUBMITTED", "TRIAGED", "triage"),
            (3, "TRIAGED", "ASSIGNED", "assign"),
            (4, "ASSIGNED", "IN_PROGRESS", "start"),
            (5, "IN_PROGRESS", "RESOLVED", "resolve"),
        ]:
            params.update(
                version=version,
                source=source,
                target=target,
                action=action,
                event=uuid4(),
                actor=world.manager.user_id if version < 4 else world.colleague.user_id,
            )
            extra = (
                ",assigned_to=:assignee"
                if version == 3
                else ",resolution='Trusted original resolution'"
                if version == 5
                else ""
            )
            connection.execute(
                text(f"UPDATE requests SET status=:target,version=:version{extra} WHERE id=:id"),
                params,
            )
            connection.execute(
                text(
                    "INSERT INTO request_events(id,organization_id,request_id,sequence"
                    ",actor_id,action,from_state,to_state,reason,at) VALUES(:event,:or"
                    "g,:id,:version,:actor,:action,:source,:target,'Original service w"
                    "ork',now())"
                ),
                params,
            )
    if corrupt:
        with world.engine.begin() as connection:
            connection.execute(text("ALTER TABLE requests DISABLE TRIGGER USER"))
            connection.execute(text("UPDATE requests SET resolution=NULL WHERE id=:id"), params)
            connection.execute(text("ALTER TABLE requests ENABLE TRIGGER USER"))
    with world.engine.connect() as connection:
        before = connection.execute(
            text(
                "SELECT to_jsonb(e)::text FROM request_events e WHERE request_id=:"
                "id ORDER BY sequence"
            ),
            params,
        ).all()
    command.upgrade(configuration, "head")
    command.check(configuration)
    configure_reopen(world)
    with Session(world.engine) as session:
        record = get_request(session, world.owner, draft.id)
    from app.services.capabilities import get_capabilities

    with Session(world.engine) as session:
        capability = get_capabilities(session, world.owner, draft.id)
        assert ("reopen" in {entry.action.value for entry in capability.available_actions}) == (
            not corrupt
        )
        assert all(entry.resolution_id is None for entry in capability.available_actions)
    with world.engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM service_resolutions")) == 0
    if corrupt:
        with pytest.raises(DomainError) as error:
            world.act(record, world.owner, "reopen")
        assert error.value.status == 409
        with world.engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM service_resolutions")) == 0
    else:
        record = world.act(record, world.owner, "reopen").request
        with world.engine.connect() as connection:
            captured = connection.execute(
                text(
                    "SELECT actor_id,captured_by,body FROM service_resolutions WHERE request_id=:id"
                ),
                params,
            ).one()
            assert (
                captured.actor_id == world.colleague.user_id
                and captured.captured_by == world.owner.user_id
            )
            assert captured.body == "Trusted original resolution"
        record = world.act(record, world.colleague, "start").request
        record = world.act(record, world.colleague, "resolve", resolution="Fresh cycle").request
        assert world.act(record, world.owner, "close").request.status == "CLOSED"
    with world.engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT to_jsonb(e)::text FROM request_events e WHERE request_id=:"
                    "id AND sequence<=5 ORDER BY sequence"
                ),
                params,
            ).all()
            == before
        )


def test_downgrade_refuses_lifecycle_evidence(world: World) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.exc import DBAPIError

    from tests.lifecycle_cases import held

    held(world)
    with pytest.raises(DBAPIError, match="downgrade blocked"):
        command.downgrade(Config("alembic.ini"), "0005_revisions")


def test_lifecycle_http_uses_real_sessions_and_csrf(
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
    from tests.lifecycle_cases import approved

    origin = "http://127.0.0.1:8000"
    monkeypatch.setenv("ACTIONDESK_AUTH_ORGANIZATION_SLUG", str(world.owner.organization_id))
    get_auth_settings.cache_clear()
    credentials: dict[str, dict[str, str]] = {}
    with Session(world.engine) as session, session.begin():
        for label, actor in (
            ("owner", world.owner),
            ("manager", world.manager),
            ("admin", world.admin),
        ):
            user = session.get(User, actor.user_id)
            assert user
            password = secrets.token_urlsafe(24)
            replace_password(session, user, password_hasher().hash(password))
            credentials[label] = {"email": user.email, "password": password}
    app.dependency_overrides[login_limiter] = lambda: UnthrottledFixture()
    record = approved(world)
    url = f"/requests/{record.id}/transitions"
    try:
        with TestClient(app, base_url=origin) as client:
            body: dict[str, object] = {
                "action": "request_reversal",
                "intent": "correct",
                "expected_version": record.version,
                "reason": "Correct approved expense",
            }
            assert client.post(url, json=body, headers={"Origin": origin}).status_code == 401
            login = client.post(
                "/auth/login", json=credentials["owner"], headers={"Origin": origin}
            )
            assert login.status_code == 200
            headers = {
                "Origin": origin,
                "X-CSRF-Token": login.json()["csrf_token"],
                "Idempotency-Key": str(uuid4()),
            }
            assert client.post(url, json=body, headers={"Origin": origin}).status_code == 403
            response = client.post(url, json=body, headers=headers)
            assert response.status_code == 200, response.text
            hold = response.json()["request"]
            body = {
                "action": "approve_reversal",
                "expected_version": hold["version"],
                "reason": "Independent review",
                "reversal_request_id": hold["active_reversal"]["id"],
            }
            headers["Idempotency-Key"] = str(uuid4())
            assert client.post(url, json=body, headers=headers).status_code == 403
            login = client.post(
                "/auth/login", json=credentials["manager"], headers={"Origin": origin}
            )
            assert login.status_code == 200
            headers["X-CSRF-Token"] = login.json()["csrf_token"]
            assert client.get("/reversals").status_code == 200
            response = client.post(url, json=body, headers=headers)
            assert response.status_code == 200, response.text
            reversed_request = response.json()["request"]
            login = client.post(
                "/auth/login", json=credentials["owner"], headers={"Origin": origin}
            )
            assert login.status_code == 200
            headers["X-CSRF-Token"] = login.json()["csrf_token"]
            headers["Idempotency-Key"] = str(uuid4())
            body = {
                "action": "create_correction",
                "expected_version": reversed_request["version"],
                "reason": "Replacement intake",
                "reversal_request_id": hold["active_reversal"]["id"],
            }
            response = client.post(url, json=body, headers=headers)
            assert response.status_code == 200, response.text
            child_id = response.json()["outcome"]["related_request_id"]
            retry = client.post(url, json=body, headers=headers)
            assert (
                retry.status_code == 200
                and retry.json()["outcome"]["related_request_id"] == child_id
            )
            assert client.get(f"/requests/{child_id}").json()["status"] == "DRAFT"
            assert client.get(f"/requests/{record.id}/lifecycle").status_code == 200
            login = client.post(
                "/auth/login", json=credentials["admin"], headers={"Origin": origin}
            )
            assert login.status_code == 200
            assert client.get(f"/requests/{record.id}/lifecycle").status_code == 404
            assert client.get(f"/requests/{child_id}").status_code == 404
            assert client.get("/reversals").json()["items"] == []
    finally:
        app.dependency_overrides.clear()
        get_auth_settings.cache_clear()
