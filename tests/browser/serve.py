"""Disposable real PostgreSQL/Redis API for browser checks. Never imported by runtime.

Run in a one-off Compose API container; only the generated test database is dropped.
"""

import asyncio
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import FastAPI, HTTPException
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, JsonValue
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.auth_config import get_auth_settings
from app.core.config import get_settings
from app.db.models import AuthSession, Request, RoleAssignment, User
from app.db.seed import fixture_id, seed
from app.db.session import get_engine
from app.domain.types import Role
from app.main import app
from app.services.auth import replace_password
from app.services.passwords import password_hasher


class ReadFixture(BaseModel):
    status: int = Field(default=200, ge=200, le=599)
    body: JsonValue = None
    hold: bool = False


def main() -> None:
    url = make_url(get_settings().database_url)
    name = "actiondesk_test_browser_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    os.environ["ACTIONDESK_DATABASE_URL"] = url.set(database=name).render_as_string(
        hide_password=False
    )
    os.environ["ACTIONDESK_AUTH_SECRET"] = secrets.token_hex(32)
    os.environ["ACTIONDESK_AUTH_IP_LIMIT"] = "1000"
    os.environ["ACTIONDESK_AUTH_ACCOUNT_LIMIT"] = "1000"
    os.environ["ACTIONDESK_AUTH_ORGANIZATION_SLUG"] = "synthetic-demo"
    os.environ["ACTIONDESK_AUTH_COOKIE_SECURE"] = "false"
    os.environ["ACTIONDESK_AUTH_ALLOWED_ORIGINS"] = '["http://127.0.0.1:3100"]'
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_auth_settings.cache_clear()
    engine = get_engine()
    password = secrets.token_urlsafe(24)
    manager_password = secrets.token_urlsafe(24)
    command.upgrade(Config("alembic.ini"), "head")
    command.check(Config("alembic.ini"))
    seed(engine, 100)
    with Session(engine) as session, session.begin():
        user = session.get(User, fixture_id("user/employee"))
        assert user
        replace_password(session, user, password_hasher().hash(password))
        user.status = "active"
        manager = session.get(User, fixture_id("user/manager"))
        assert manager
        replace_password(session, manager, password_hasher().hash(manager_password))
        manager.status = "active"
        for role in (Role.MANAGER, Role.FINANCE):
            session.add(
                RoleAssignment(organization_id=user.organization_id, user_id=user.id, role=role)
            )
    faults: dict[str, int | str] = {}
    # Test-only response sequences for deterministic read composition and loading checks.
    # Real authentication and session restoration still use the unchanged application.
    read_fixtures: dict[str, list[ReadFixture]] = {}
    read_gate = asyncio.Event()

    @app.post("/__browser/reads")
    async def configure_reads(payload: dict[str, list[ReadFixture]]) -> dict[str, bool]:
        if any(
            not (
                path.split("?")[0] == "/requests"
                or path.startswith(("/requests/", "/work-queues/"))
            )
            for path in payload
        ):
            raise HTTPException(422, "Only workflow read fixtures are supported.")
        read_fixtures.clear()
        read_fixtures.update(payload)
        read_gate.clear()
        return {"ok": True}

    @app.post("/__browser/reads/release")
    async def release_reads() -> dict[str, bool]:
        read_gate.set()
        return {"ok": True}

    @app.get("/__browser/credentials")
    def credentials() -> dict[str, str]:
        return {"email": "employee@actiondesk.ahmad", "password": password}

    @app.get("/__browser/credentials/manager")
    def manager_credentials() -> dict[str, str]:
        return {"email": "manager@actiondesk.ahmad", "password": manager_password}

    @app.post("/__browser/reset")
    async def reset() -> dict[str, bool]:
        faults.clear()
        read_fixtures.clear()
        read_gate.set()
        with Session(engine) as session, session.begin():
            session.execute(text("DELETE FROM auth_sessions"))
        return {"ok": True}

    @app.post("/__browser/clear")
    def clear_fault() -> dict[str, bool]:
        faults.clear()
        return {"ok": True}

    @app.post("/__browser/fault/{status}")
    def fault(status: int) -> dict[str, bool]:
        faults["status"] = status
        faults["target"] = "login"
        return {"ok": True}

    @app.post("/__browser/fault/{status}/requests")
    def read_fault(status: int) -> dict[str, bool]:
        faults["status"] = status
        faults["target"] = "requests"
        return {"ok": True}

    @app.post("/__browser/expire")
    def expire() -> dict[str, bool]:
        with Session(engine) as session, session.begin():
            sessions = session.scalars(select(AuthSession))
            for authentication in sessions:
                authentication.revoked_at = authentication.created_at
        return {"ok": True}

    @app.get("/__browser/record")
    def record() -> dict[str, str]:
        with engine.connect() as connection:
            return {"id": str(connection.scalar(select(Request.id).limit(1)))}

    @app.middleware("http")
    async def failures(request: HTTPRequest, call_next: object) -> object:
        # Fixture-only injected HTTP faults; real application routes otherwise remain unchanged.
        from collections.abc import Awaitable, Callable
        from typing import cast

        from starlette.responses import Response

        query_path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        fixtures = read_fixtures.get(query_path, read_fixtures.get(request.url.path))
        if request.method == "GET" and fixtures:
            selected = fixtures.pop(0) if len(fixtures) > 1 else fixtures[0]
            if selected.hold:
                await read_gate.wait()
            return JSONResponse(
                selected.body,
                status_code=selected.status,
                headers={"Cache-Control": "no-store", "X-Request-ID": "browser-read-fixture"},
            )
        if faults.get("status") and (
            request.url.path == "/auth/login"
            if faults.get("target") == "login"
            else request.url.path.startswith("/requests")
        ):
            status = int(faults["status"])
            return JSONResponse(
                {"title": "Synthetic test fault", "detail": "Controlled browser test response."},
                status_code=status,
                headers={"Retry-After": "1", "X-Request-ID": "browser-fixture-fault"},
            )
        return await cast(Callable[[HTTPRequest], Awaitable[Response]], call_next)(request)

    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            async with original(app):
                yield
        finally:
            engine.dispose()
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
            admin.dispose()

    app.router.lifespan_context = lifespan
    uvicorn.run(app, host="0.0.0.0", port=8010, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
