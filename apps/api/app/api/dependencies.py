import hmac
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.auth_config import get_auth_settings
from app.db.session import get_engine
from app.domain.errors import DomainError
from app.domain.identity import Principal
from app.services import auth


def require_origin(request: Request) -> None:
    if request.headers.get("origin") not in get_auth_settings().allowed_origins:
        raise DomainError(403, "Forbidden", "Request origin is not permitted.")


def authenticated_context(request: Request) -> auth.AuthContext:
    context = auth.authenticate(get_engine(), request.cookies.get(get_auth_settings().cookie_name))
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(request)
        supplied = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(supplied.encode(), context.response.csrf_token.encode()):
            raise DomainError(403, "Forbidden", "CSRF verification failed.")
    return context


def authenticated_principal(request: Request) -> Principal:
    return authenticated_context(request).principal


def database_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
