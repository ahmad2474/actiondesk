import re
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse

from app.api.requests import router as requests_router
from app.core.config import get_settings
from app.domain.errors import DomainError
from app.schemas.core import Problem

EXPECTED_REVISION = "0002_request_foundation"


class Health(BaseModel):
    status: Literal["ok"]


class DependencyChecks(BaseModel):
    database: Literal["ok", "unavailable"]
    migrations: Literal["ok", "unavailable"]
    redis: Literal["ok", "unavailable"]


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: DependencyChecks


app = FastAPI(title="ActionDesk API", version="0.0.1")
app.include_router(requests_router)


@app.exception_handler(DomainError)
async def domain_error(request: Request, error: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        media_type="application/problem+json",
        content=Problem(title=error.title, status=error.status, detail=error.detail).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def invalid_input(request: Request, error: RequestValidationError) -> JSONResponse:
    # Pydantic error inputs can include sensitive request text. Never echo them.
    return JSONResponse(
        status_code=422,
        media_type="application/problem+json",
        content=Problem(
            title="Unprocessable Content", status=422, detail="Request input is invalid."
        ).model_dump(),
    )


@app.middleware("http")
async def request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
    supplied = request.headers.get("X-Request-ID", "")
    identifier = supplied if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied) else str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = identifier
    return response


def dependency_checks() -> DependencyChecks:
    checks = DependencyChecks(database="unavailable", migrations="unavailable", redis="unavailable")
    try:
        from sqlalchemy import text

        from app.db.session import get_engine

        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
            checks.database = "ok"
            revisions = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars()
            if list(revisions) == [EXPECTED_REVISION]:
                checks.migrations = "ok"
    except Exception:
        # Connection/schema errors must not expose URLs, credentials, or internal exception text.
        pass
    try:
        from redis import Redis

        with Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
        ) as client:
            if client.ping():
                checks.redis = "ok"
    except Exception:
        pass
    return checks


@app.get("/health", response_model=Health, operation_id="get_health", tags=["Operations"])
def health() -> Health:
    return Health(status="ok")


@app.get(
    "/ready",
    response_model=Readiness,
    operation_id="get_readiness",
    tags=["Operations"],
    responses={503: {"model": Readiness, "description": "Dependencies or migrations unavailable"}},
)
def ready(response: Response) -> Readiness:
    checks = dependency_checks()
    is_ready = all(value == "ok" for value in checks.model_dump().values())
    response.status_code = 200 if is_ready else 503
    return Readiness(status="ready" if is_ready else "not_ready", checks=checks)
