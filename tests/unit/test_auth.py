"""API/session tests using an explicit password adapter; real Argon2 tests are separate."""

import hashlib
import hmac
import secrets
from collections.abc import Iterator
from datetime import UTC, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import auth as api_auth
from app.api import dependencies
from app.core.auth_config import get_auth_settings
from app.db.models import AuthSession, RoleAssignment, User
from app.domain.email import canonical_email
from app.domain.errors import DomainError
from app.main import app
from app.services import auth
from app.services.login_limits import login_limiter
from tests.unit.support import provision

ORIGIN = "http://127.0.0.1:8000"


class PasswordStub:
    def hash(self, password: str) -> str:
        return "unit-adapter:" + hashlib.sha256(password.encode()).hexdigest()

    def check_needs_rehash(self, hash: str) -> bool:
        return False


class LimiterStub:
    def check(self, address: str, email: str) -> None:
        pass


@pytest.fixture
def auth_case(unit_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    principal, department = provision(unit_engine)
    password = secrets.token_urlsafe(24)
    with Session(unit_engine) as session, session.begin():
        user = session.get(User, principal.user_id)
        assert user is not None
        user.password_hash = PasswordStub().hash(password)
        email = user.email
    monkeypatch.setenv("ACTIONDESK_AUTH_ORGANIZATION_SLUG", str(principal.organization_id))
    get_auth_settings.cache_clear()
    monkeypatch.setattr(auth, "password_hasher", lambda: PasswordStub())
    monkeypatch.setattr(
        auth,
        "verify_password",
        lambda encoded, value: hmac.compare_digest(encoded or "", PasswordStub().hash(value)),
    )
    monkeypatch.setattr(api_auth, "get_engine", lambda: unit_engine)
    monkeypatch.setattr(dependencies, "get_engine", lambda: unit_engine)

    def database() -> Iterator[Session]:
        with Session(unit_engine) as session:
            yield session

    app.dependency_overrides[dependencies.database_session] = database
    app.dependency_overrides[login_limiter] = lambda: LimiterStub()
    yield {
        "email": email,
        "password": password,
        "user": str(principal.user_id),
        "department": str(department),
    }
    app.dependency_overrides.clear()


def sign_in(client: TestClient, case: dict[str, str]) -> str:
    response = client.post(
        "/auth/login",
        json={"email": case["email"], "password": case["password"]},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return str(response.json()["csrf_token"])


def test_login_cookie_current_user_and_protected_creation(
    auth_case: dict[str, str], unit_engine: Engine
) -> None:
    with TestClient(app, base_url=ORIGIN) as client:
        csrf = sign_in(client, auth_case)
        cookie = client.cookies.get(get_auth_settings().cookie_name)
        assert cookie is not None and len(cookie) == 43
        me = client.get("/auth/me")
        assert me.json()["user"]["id"] == auth_case["user"]
        assert me.json()["user"]["roles"] == ["employee"]
        assert "password_hash" not in me.text and cookie not in me.text
        assert client.get("/requests").status_code == 200
        body = {
            "department_id": auth_case["department"],
            "title": "Synthetic",
            "raw_text": "Test",
            "type": "service",
        }
        headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": secrets.token_hex(16)}
        created = client.post("/requests", json=body, headers=headers)
        assert created.status_code == 201, created.text
        assert created.json()["created_by"] == auth_case["user"]
        assert (
            client.post(
                "/requests", json={**body, "requester_id": auth_case["user"]}, headers=headers
            ).status_code
            == 422
        )
        with Session(unit_engine) as session:
            record = session.scalar(select(AuthSession))
            assert record is not None and record.token_hash == auth.token_digest(cookie)
            assert record.token_hash != cookie


@pytest.mark.parametrize("kind", ["unknown", "wrong", "inactive", "passwordless"])
def test_generic_invalid_login(kind: str, auth_case: dict[str, str], unit_engine: Engine) -> None:
    data = {"email": auth_case["email"], "password": auth_case["password"]}
    if kind == "unknown":
        data["email"] = "unknown@example.invalid"
    elif kind == "wrong":
        data["password"] = secrets.token_urlsafe(24)
    else:
        with Session(unit_engine) as session, session.begin():
            user = session.get(User, UUID(auth_case["user"]))
            # UUID columns require UUID values, not textual IDs.
            if user is None:
                raise AssertionError("Missing test user")
            if kind == "inactive":
                user.status = "inactive"
            else:
                user.password_hash = None
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.post("/auth/login", json=data, headers={"Origin": ORIGIN})
        assert response.status_code == 401
        assert response.json()["detail"] == "Valid authentication is required."
        assert "set-cookie" not in response.headers
        assert response.headers["cache-control"] == "no-store"


def test_csrf_and_origin_enforcement(auth_case: dict[str, str]) -> None:
    with TestClient(app, base_url=ORIGIN) as client:
        csrf = sign_in(client, auth_case)
        assert client.get("/auth/me").status_code == 200  # No CSRF on safe reads.
        for headers in (
            {},
            {"Origin": ORIGIN},
            {"Origin": ORIGIN, "X-CSRF-Token": "wrong"},
            {"Origin": "https://untrusted.invalid", "X-CSRF-Token": csrf},
        ):
            assert client.post("/auth/logout", headers=headers).status_code == 403
            assert client.get("/auth/me").status_code == 200
        assert (
            client.post(
                "/auth/login", json={"email": auth_case["email"], "password": auth_case["password"]}
            ).status_code
            == 403
        )


def test_device_sessions_replacement_logout_and_replay(
    auth_case: dict[str, str], unit_engine: Engine
) -> None:
    with TestClient(app, base_url=ORIGIN) as first, TestClient(app, base_url=ORIGIN) as second:
        first_csrf = sign_in(first, auth_case)
        sign_in(second, auth_case)
        old = first.cookies.get(get_auth_settings().cookie_name)
        new_csrf = sign_in(first, auth_case)
        assert new_csrf != first_csrf
        assert second.get("/auth/me").status_code == 200
        assert (
            first.post(
                "/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": new_csrf}
            ).status_code
            == 204
        )
        assert first.get("/auth/me").status_code == 401
        first.cookies.set(get_auth_settings().cookie_name, old or "")
        assert first.get("/auth/me").status_code == 401
        assert first.post("/auth/logout", headers={"Origin": ORIGIN}).status_code == 204
        assert second.get("/auth/me").status_code == 200
    with Session(unit_engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.revoked_at.is_(None))
            )
            == 1
        )


def test_session_touch_and_expiry(
    auth_case: dict[str, str], unit_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = auth.utc_now()
    clock = {"now": initial}
    monkeypatch.setattr(auth, "utc_now", lambda: clock["now"])
    with TestClient(app, base_url=ORIGIN) as client:
        sign_in(client, auth_case)
        writes: list[str] = []

        def record_write(
            connection: object,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            if statement.startswith("UPDATE auth_sessions"):
                writes.append(statement)

        event.listen(unit_engine, "before_cursor_execute", record_write)
        try:
            clock["now"] = initial + timedelta(seconds=299)
            assert client.get("/auth/me").status_code == 200
            assert not writes
            clock["now"] = initial + timedelta(seconds=301)
            assert client.get("/auth/me").status_code == 200
            assert len(writes) == 1
            assert client.get("/auth/me").status_code == 200
            assert len(writes) == 1
            clock["now"] = initial + timedelta(seconds=2102)
            assert client.get("/auth/me").status_code == 401
        finally:
            event.remove(unit_engine, "before_cursor_execute", record_write)
        with Session(unit_engine) as session:
            row = session.scalar(select(AuthSession))
            assert row is not None
            assert row.expires_at.replace(tzinfo=UTC) == initial + timedelta(hours=8)


def test_absolute_expiry_and_tampering(
    auth_case: dict[str, str], unit_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = auth.utc_now()
    monkeypatch.setattr(auth, "utc_now", lambda: initial)
    with TestClient(app, base_url=ORIGIN) as client:
        sign_in(client, auth_case)
        token = client.cookies.get(get_auth_settings().cookie_name)
        assert token is not None
        with Session(unit_engine) as session, session.begin():
            row = session.scalar(select(AuthSession))
            assert row is not None
            row.last_seen_at = initial + timedelta(hours=8) - timedelta(seconds=1)
        monkeypatch.setattr(auth, "utc_now", lambda: initial + timedelta(hours=8))
        assert client.get("/auth/me").status_code == 401
        for bad_token in (secrets.token_urlsafe(32), "malformed", token[:-1] + "!"):
            client.cookies.set(get_auth_settings().cookie_name, bad_token)
            assert client.get("/auth/me").status_code == 401


def test_current_roles_and_inactive_user(auth_case: dict[str, str], unit_engine: Engine) -> None:
    from uuid import UUID

    with TestClient(app, base_url=ORIGIN) as client:
        sign_in(client, auth_case)
        with Session(unit_engine) as session, session.begin():
            session.query(RoleAssignment).update({"revoked_at": auth.utc_now()})
        assert client.get("/auth/me").json()["user"]["roles"] == []
        assert client.get("/requests").status_code == 403
        with Session(unit_engine) as session, session.begin():
            user = session.get(User, UUID(auth_case["user"]))
            assert user is not None
            user.status = "inactive"
        assert client.get("/auth/me").status_code == 401


def test_email_case_and_tenant_isolation(auth_case: dict[str, str], unit_engine: Engine) -> None:
    other, _ = provision(unit_engine)
    with Session(unit_engine) as session, session.begin():
        user = session.get(User, other.user_id)
        assert user is not None
        user.email = auth_case["email"]
        user.password_hash = PasswordStub().hash(secrets.token_urlsafe(24))
    with TestClient(app, base_url=ORIGIN) as client:
        sign_in(client, {**auth_case, "email": " " + auth_case["email"].upper() + " "})
        assert client.get("/auth/me").json()["user"]["id"] == auth_case["user"]
    with pytest.raises(IntegrityError), Session(unit_engine) as session, session.begin():
        from uuid import UUID

        session.add(
            User(
                organization_id=UUID(get_auth_settings().organization_slug),
                email=auth_case["email"].upper(),
                name="Duplicate",
            )
        )
    assert canonical_email(" User@Example.Invalid ") == "user@example.invalid"
    from app.domain.types import Role
    from app.schemas.core import UserCreate

    assert (
        UserCreate(
            email=" User@Example.Invalid ", name="Synthetic", roles=frozenset({Role.EMPLOYEE})
        ).email
        == "user@example.invalid"
    )
    with pytest.raises(ValueError):
        canonical_email("\tuser@example.invalid")


def test_redis_failure_and_no_authenticated_dependency(
    auth_case: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:

    def unavailable(*args: object, **kwargs: object) -> None:
        raise RedisConnectionError("Sensitive connection text")

    with TestClient(app, base_url=ORIGIN) as client:
        sign_in(client, auth_case)
        app.dependency_overrides.pop(login_limiter)
        monkeypatch.setattr("app.services.login_limits.Redis.from_url", unavailable)
        failed = client.post(
            "/auth/login",
            json={"email": auth_case["email"], "password": auth_case["password"]},
            headers={"Origin": ORIGIN},
        )
        assert failed.status_code == 503 and "Sensitive" not in failed.text
        assert client.get("/requests").status_code == 200
        assert client.get("/auth/me").status_code == 200


def test_runtime_overrides_and_settings_are_explicit() -> None:
    assert dependencies.authenticated_principal not in app.dependency_overrides
    settings = get_auth_settings()
    settings.validate_runtime()
    assert settings.cookie_name == "actiondesk_session_local"
    settings.cookie_secure = True
    assert settings.cookie_name.startswith("__Host-")
    for origins in (["*"], ["https://example.invalid/path"]):
        settings.allowed_origins = origins
        with pytest.raises(RuntimeError):
            settings.validate_runtime()


def test_local_config_initialization_preserves_secrets(tmp_path: Path) -> None:
    from scripts.init_auth_config import initialize

    path = tmp_path / ".env"
    path.write_text("# Local\nACTIONDESK_AUTH_SECRET=\n")
    initialize(path)
    first = path.read_text()
    initialize(path)
    assert path.read_text() == first
    assert path.stat().st_mode & 0o777 == 0o600


def test_secure_cookie_and_exact_cors(auth_case: dict[str, str]) -> None:
    settings = get_auth_settings()
    settings.cookie_secure = True
    settings.allowed_origins = ["https://127.0.0.1:8000"]
    with TestClient(app, base_url="https://127.0.0.1:8000") as client:
        result = client.post(
            "/auth/login",
            json={"email": auth_case["email"], "password": auth_case["password"]},
            headers={"Origin": settings.allowed_origins[0]},
        )
        assert result.status_code == 200
        cookie = result.headers["set-cookie"]
        assert cookie.startswith("__Host-actiondesk_session=")
        assert all(
            value in cookie.lower() for value in ("httponly", "secure", "samesite=lax", "path=/")
        )
        assert "domain=" not in cookie.lower()
        assert client.get("/auth/me").status_code == 200
        for origin, code in (
            (settings.allowed_origins[0], 200),
            ("https://untrusted.invalid", 400),
        ):
            result = client.options(
                "/auth/login",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert result.status_code == code
            assert result.headers.get("access-control-allow-origin") != "*"
            if code == 200:
                assert result.headers["access-control-allow-origin"] == origin
                assert result.headers["access-control-allow-credentials"] == "true"


def test_login_requires_json_and_ignores_forwarded_identity(auth_case: dict[str, str]) -> None:
    addresses: list[str] = []

    class CapturingLimiter:
        def check(self, address: str, email: str) -> None:
            addresses.append(address)

    app.dependency_overrides[login_limiter] = lambda: CapturingLimiter()
    with TestClient(app, base_url=ORIGIN) as client:
        result = client.post(
            "/auth/login",
            content="not JSON",
            headers={"Origin": ORIGIN, "Content-Type": "text/plain"},
        )
        assert result.status_code == 415 and not addresses
        result = client.post(
            "/auth/login",
            json={"email": auth_case["email"], "password": auth_case["password"]},
            headers={"Origin": ORIGIN, "X-Forwarded-For": "spoofed", "Forwarded": "for=spoofed"},
        )
        assert result.status_code == 200
        assert addresses == ["testclient"]


def test_login_rate_limit_returns_retry_after(auth_case: dict[str, str]) -> None:
    class Limited:
        def check(self, address: str, email: str) -> None:
            raise DomainError(
                429, "Too Many Requests", "Try login again later.", headers={"Retry-After": "60"}
            )

    app.dependency_overrides[login_limiter] = lambda: Limited()
    with TestClient(app, base_url=ORIGIN) as client:
        result = client.post(
            "/auth/login",
            json={"email": auth_case["email"], "password": auth_case["password"]},
            headers={"Origin": ORIGIN},
        )
        assert result.status_code == 429
        assert result.headers["retry-after"] == "60"
        assert result.headers["cache-control"] == "no-store"
        assert "set-cookie" not in result.headers


def test_explicit_initialization_and_password_revocation(
    auth_case: dict[str, str], unit_engine: Engine
) -> None:
    new, _ = provision(unit_engine, UUID(get_auth_settings().organization_slug))
    with Session(unit_engine) as session:
        user = session.get(User, new.user_id)
        assert user is not None
        email = user.email
    password = secrets.token_urlsafe(24)
    auth.set_initial_password(unit_engine, email, password)
    with pytest.raises(ValueError):
        auth.set_initial_password(unit_engine, email, password)
    with TestClient(app, base_url=ORIGIN) as first, TestClient(app, base_url=ORIGIN) as second:
        sign_in(first, auth_case)
        sign_in(second, auth_case)
        with Session(unit_engine) as session, session.begin():
            user = session.get(User, UUID(auth_case["user"]))
            assert user is not None
            auth.replace_password(session, user, PasswordStub().hash(secrets.token_urlsafe(24)))
        assert first.get("/auth/me").status_code == second.get("/auth/me").status_code == 401
