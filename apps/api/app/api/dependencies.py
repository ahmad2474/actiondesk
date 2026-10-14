from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.domain.errors import DomainError
from app.domain.identity import Principal


def authenticated_principal() -> Principal:
    # Login/session verification is outside milestone 1. No client-supplied identity fallback.
    raise DomainError(401, "Unauthorized", "A verified authenticated identity is required.")


def database_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
