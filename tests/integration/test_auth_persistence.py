"""Real PostgreSQL session/migration and Redis login limiter tests. No identity overrides."""

import secrets
from collections.abc import Iterator
from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.auth_config import get_auth_settings
from app.db.models import AuthSession, Organization, User
from app.db.seed import fixture_id, seed
from app.domain.errors import DomainError
from app.main import app
from app.services import auth
from app.services.login_limits import RedisLoginLimiter, login_limiter
from app.services.passwords import password_hasher

pytestmark = pytest.mark.integration
ORIGIN = "http://127.0.0.1:8000"


class UnthrottledFixture:
    def check(self, address: str, email: str) -> None:
        pass


@pytest.fixture
def account(database: Engine) -> dict[str, str]:
    seed(database, 10)
    password = secrets.token_urlsafe(24)
    with Session(database) as session, session.begin():
        user = session.get(User, fixture_id("user/employee"))
        assert user is not None
        auth.replace_password(session, user, password_hasher().hash(password))
        user.status = "active"
    return {"email": "employee@actiondesk.invalid", "password": password}


@pytest.fixture
def client(account: dict[str, str]) -> Iterator[TestClient]:
    # Only the limiter is isolated here. The real database-backed identity dependency runs.
    app.dependency_overrides[login_limiter] = lambda: UnthrottledFixture()
    try:
        with TestClient(app, base_url=ORIGIN) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def login(client: TestClient, account: dict[str, str]) -> str:
    result = client.post("/auth/login", json=account, headers={"Origin": ORIGIN})
    assert result.status_code == 200, result.text
    return str(result.json()["csrf_token"])


def test_live_login_request_ownership_and_logout(
    client: TestClient, account: dict[str, str], database: Engine
) -> None:
    assert client.get("/requests").status_code == 401
    csrf = login(client, account)
    token = client.cookies.get(get_auth_settings().cookie_name)
    assert token is not None
    assert client.get("/requests").status_code == 200
    created = client.post(
        "/requests",
        json={
            "department_id": str(fixture_id("department")),
            "type": "service",
            "title": "Synthetic authenticated request",
            "raw_text": "Synthetic",
        },
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": secrets.token_hex(16)},
    )
    assert created.status_code == 201, created.text
    assert created.json()["created_by"] == str(fixture_id("user/employee"))
    assert len(created.json()["status_history"]) == 1
    with Session(database) as session:
        record = session.scalar(select(AuthSession))
        assert record is not None and record.token_hash == auth.token_digest(token)
    assert (
        client.post("/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}).status_code
        == 204
    )
    client.cookies.set(get_auth_settings().cookie_name, token)
    assert client.get("/requests").status_code == 401


def test_disable_reenable_never_revives_sessions(
    client: TestClient, account: dict[str, str], database: Engine
) -> None:
    login(client, account)
    with database.begin() as connection:
        connection.execute(
            text("UPDATE users SET status='inactive' WHERE id=:id"),
            {"id": fixture_id("user/employee")},
        )
    with Session(database) as session:
        assert session.scalar(select(AuthSession.revoked_at)) is not None
    with database.begin() as connection:
        connection.execute(
            text("UPDATE users SET status='active' WHERE id=:id"),
            {"id": fixture_id("user/employee")},
        )
    assert client.get("/auth/me").status_code == 401


def test_explicit_password_change_revokes_all_devices(
    client: TestClient, account: dict[str, str], database: Engine
) -> None:
    login(client, account)
    with TestClient(app, base_url=ORIGIN) as other:
        login(other, account)
        with Session(database) as session, session.begin():
            user = session.get(User, fixture_id("user/employee"))
            assert user is not None
            auth.replace_password(session, user, password_hasher().hash(secrets.token_urlsafe(24)))
        assert client.get("/auth/me").status_code == other.get("/auth/me").status_code == 401
    with Session(database) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.revoked_at.is_(None))
            )
            == 0
        )


def test_login_rehash_preserves_other_device(client: TestClient, account: dict[str, str]) -> None:
    login(client, account)
    with TestClient(app, base_url=ORIGIN) as other:
        login(other, account)
        settings = get_auth_settings()
        settings.argon_time_cost += 1
        password_hasher.cache_clear()
        login(client, account)
        assert client.get("/auth/me").status_code == 200
        assert other.get("/auth/me").status_code == 200


def test_session_constraints_and_email_uniqueness(database: Engine) -> None:
    seed(database, 10)
    with pytest.raises(IntegrityError) as error, database.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users(id,organization_id,email,name) "
                "VALUES(:id,:org,' Employee@ActionDesk.Invalid ','Duplicate')"
            ),
            {"id": fixture_id("collision"), "org": fixture_id("organization")},
        )
    assert getattr(error.value.orig, "sqlstate", None) == "23505"
    with Session(database) as session, session.begin():
        other = Organization(slug="other", name="Other synthetic")
        session.add(other)
        session.flush()
        session.add(
            User(organization_id=other.id, email="employee@actiondesk.invalid", name="Other")
        )
    with pytest.raises(IntegrityError), Session(database) as session, session.begin():
        now = auth.utc_now()
        session.add(
            AuthSession(
                token_hash=secrets.token_hex(32),
                organization_id=fixture_id("organization"),
                user_id=fixture_id("nonexistent"),
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=8),
            )
        )


def test_email_collision_migration_fails_without_rewriting(database: Engine) -> None:
    seed(database, 10)
    configuration = Config("alembic.ini")
    command.downgrade(configuration, "0002_request_foundation")
    with database.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users(id,organization_id,email,name) "
                "VALUES(:id,:org,'EMPLOYEE@ACTIONDESK.INVALID','Collision')"
            ),
            {"id": fixture_id("collision"), "org": fixture_id("organization")},
        )
    with pytest.raises(DBAPIError, match="Canonical email collision"):
        command.upgrade(configuration, "head")
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM users")) == 5
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0002_request_foundation"
        )


def test_real_redis_login_throttle(database: Engine) -> None:
    settings = get_auth_settings()
    settings.ip_limit = 2
    settings.account_limit = 10
    limiter = RedisLoginLimiter()
    address, email = secrets.token_hex(16), f"{secrets.token_hex(16)}@example.invalid"
    limiter.check(address, email)
    limiter.check(address, email)
    with pytest.raises(DomainError) as error:
        limiter.check(address, email)
    assert error.value.status == 429
    assert int(error.value.headers["Retry-After"]) > 0


def test_live_workflow_mutation_requires_session_origin_and_csrf(
    client: TestClient, account: dict[str, str], database: Engine
) -> None:
    csrf = login(client, account)
    created = client.post(
        "/requests",
        json={
            "department_id": str(fixture_id("department")),
            "type": "expense",
            "title": "Synthetic withdrawal",
            "raw_text": "Synthetic",
        },
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": secrets.token_hex(16)},
    )
    assert created.status_code == 201
    url = f"/requests/{created.json()['id']}/transitions"
    body = {"action": "cancel", "expected_version": 1, "reason": "Synthetic withdrawal"}
    key = secrets.token_hex(16)
    for headers in (
        {"Idempotency-Key": key},
        {"Origin": ORIGIN, "Idempotency-Key": key},
        {"Origin": "http://foreign.invalid", "X-CSRF-Token": csrf, "Idempotency-Key": key},
    ):
        assert client.post(url, json=body, headers=headers).status_code == 403
    result = client.post(
        url, json=body, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": key}
    )
    assert result.status_code == 200, result.text
    assert result.json()["request"]["status"] == "WITHDRAWN"
    assert client.get("/approvals").status_code == 200
    client.post("/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert (
        client.post(
            url, json=body, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": key}
        ).status_code
        == 401
    )
    assert client.get("/approvals").status_code == 401
