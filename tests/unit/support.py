from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.compiler import TypeCompiler

from app.db.models import Base, Department, Organization, RoleAssignment, RoleDefinition, User
from app.domain.identity import Principal
from app.domain.types import Role


@compiles(JSONB, "sqlite")
def unit_test_json_type(type_: JSONB, compiler: TypeCompiler, **kwargs: object) -> str:
    return "JSON"


@pytest.fixture
def unit_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: object, record: object) -> None:
        # Unit adapter only; PostgreSQL tests use Alembic and real constraint triggers.
        from sqlite3 import Connection

        assert isinstance(connection, Connection)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.create_function("btrim", 1, lambda value: value.strip(" "), deterministic=True)

    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add_all([RoleDefinition(name=role) for role in Role])
    yield engine
    engine.dispose()


def provision(engine: Engine, organization_id: UUID | None = None) -> tuple[Principal, UUID]:
    organization, user, department = organization_id or uuid4(), uuid4(), uuid4()
    with Session(engine) as session, session.begin():
        if organization_id is None:
            session.add(Organization(id=organization, slug=str(organization), name="Synthetic"))
            session.flush()
        session.add(
            Department(id=department, organization_id=organization, name=f"Operations {department}")
        )
        session.flush()
        session.add(
            User(
                id=user,
                organization_id=organization,
                name="Synthetic",
                email=f"{user}@example.invalid",
                department_id=department,
                status="active",
            )
        )
        session.flush()
        session.add(RoleAssignment(organization_id=organization, user_id=user, role=Role.EMPLOYEE))
    return Principal(organization, user), department
