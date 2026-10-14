"""Service/API unit tests with SQLite; PostgreSQL enforcement is tested separately."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.compiler import TypeCompiler

from app.api.dependencies import authenticated_principal, database_session
from app.db.models import (
    Base,
    Department,
    Organization,
    Request,
    RequestEvent,
    RoleAssignment,
    RoleDefinition,
    User,
)
from app.domain.identity import Principal
from app.domain.types import RequestStatus, RequestType, Role, initial_request_status
from app.main import app
from app.schemas.core import DepartmentCreate, RequestCreate, UserCreate, UserRead


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


@pytest.fixture
def requester(unit_engine: Engine) -> tuple[Principal, UUID]:
    return provision(unit_engine)


@pytest.fixture
def client(unit_engine: Engine, requester: tuple[Principal, UUID]) -> Iterator[TestClient]:
    def session_override() -> Iterator[Session]:
        with Session(unit_engine) as session:
            yield session

    app.dependency_overrides[authenticated_principal] = lambda: requester[0]
    app.dependency_overrides[database_session] = session_override
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def payload(requester: tuple[Principal, UUID], kind: str = "service") -> dict[str, str]:
    return {
        "requester_id": str(requester[0].user_id),
        "department_id": str(requester[1]),
        "type": kind,
        "title": "Synthetic request",
        "raw_text": "Synthetic description",
    }


@pytest.mark.parametrize(
    "kind,status",
    [
        ("service", "SUBMITTED"),
        ("expense", "DRAFT"),
        ("leave", "DRAFT"),
    ],
)
def test_create_and_history(
    client: TestClient,
    unit_engine: Engine,
    requester: tuple[Principal, UUID],
    kind: str,
    status: str,
) -> None:
    response = client.post(
        "/requests", json=payload(requester, kind), headers={"Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["status"] == status
    assert record["version"] == 1
    assert record["created_by"] == str(requester[0].user_id)
    assert len(record["status_history"]) == 1
    history = record["status_history"][0]
    assert history["from_state"] is None
    assert history["to_state"] == status
    assert history["actor_id"] == record["created_by"]
    assert history["sequence"] == 1
    assert history["at"] == record["created_at"]
    with Session(unit_engine) as session:
        assert session.scalar(select(func.count()).select_from(Request)) == 1
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 1
        assert (
            session.scalar(select(func.count()).select_from(Base.metadata.tables["outbox_events"]))
            == 0
        )


def test_retries_and_conflicting_input(
    client: TestClient, unit_engine: Engine, requester: tuple[Principal, UUID]
) -> None:
    headers = {"Idempotency-Key": str(uuid4())}
    data = payload(requester)
    first = client.post("/requests", json=data, headers=headers)
    second = client.post("/requests", json=data, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    data["title"] = "Different"
    assert client.post("/requests", json=data, headers=headers).status_code == 409
    with Session(unit_engine) as session:
        assert session.scalar(select(func.count()).select_from(Request)) == 1
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 1


@pytest.mark.parametrize("field,expected", [("requester_id", 403), ("department_id", 422)])
def test_invalid_references_do_not_write(
    client: TestClient,
    unit_engine: Engine,
    requester: tuple[Principal, UUID],
    field: str,
    expected: int,
) -> None:
    data = payload(requester)
    data[field] = str(uuid4())
    response = client.post("/requests", json=data, headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == expected
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["x-request-id"]
    with Session(unit_engine) as session:
        assert session.scalar(select(func.count()).select_from(Request)) == 0
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 0


def test_get_list_pagination_and_ownership(
    client: TestClient, unit_engine: Engine, requester: tuple[Principal, UUID]
) -> None:
    ids = []
    for title in ("First", "Second", "Third"):
        data = payload(requester)
        data["title"] = title
        response = client.post("/requests", json=data, headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 201
        ids.append(response.json()["id"])
    assert len(client.get("/requests").json()["items"]) == 3
    page = client.get("/requests?limit=1&offset=1").json()
    assert [row["id"] for row in page["items"]] == [ids[1]]
    assert client.get(f"/requests/{ids[0]}").json()["status_history"]
    assert client.get(f"/requests/{uuid4()}").status_code == 404
    assert client.get("/requests?limit=101").status_code == 422
    assert client.get("/requests?offset=-1").status_code == 422
    other, _ = provision(unit_engine)
    app.dependency_overrides[authenticated_principal] = lambda: other
    assert client.get("/requests").json()["items"] == []
    assert client.get(f"/requests/{ids[0]}").status_code == 404
    # Same organization, different requester also cannot enumerate objects, even as admin.
    colleague, _ = provision(unit_engine, requester[0].organization_id)
    with Session(unit_engine) as session, session.begin():
        session.add(
            RoleAssignment(
                organization_id=colleague.organization_id,
                user_id=colleague.user_id,
                role=Role.ADMIN,
            )
        )
    app.dependency_overrides[authenticated_principal] = lambda: colleague
    assert client.get("/requests").json()["items"] == []
    assert client.get(f"/requests/{ids[0]}").status_code == 404


def test_unverified_identity_is_denied() -> None:
    with TestClient(app) as client:
        assert client.get("/requests").status_code == 401
        assert client.get(f"/requests/{uuid4()}").status_code == 401
        assert client.post("/requests", json={}).status_code == 401
        assert client.get("/requests", headers={"X-User-ID": str(uuid4())}).status_code == 401


def test_history_failure_rolls_back_creation(
    client: TestClient, unit_engine: Engine, requester: tuple[Principal, UUID]
) -> None:
    def fail_history(session: Session, context: object, instances: object) -> None:
        if any(isinstance(record, RequestEvent) for record in session.new):
            raise RuntimeError("Synthetic history failure")

    event.listen(Session, "before_flush", fail_history)
    try:
        with pytest.raises(RuntimeError, match="Synthetic history failure"):
            client.post(
                "/requests", json=payload(requester), headers={"Idempotency-Key": str(uuid4())}
            )
    finally:
        event.remove(Session, "before_flush", fail_history)
    with Session(unit_engine) as session:
        assert session.scalar(select(func.count()).select_from(Request)) == 0
        assert session.scalar(select(func.count()).select_from(RequestEvent)) == 0


def test_foreign_department_and_forbidden_creation_fields(
    client: TestClient, unit_engine: Engine, requester: tuple[Principal, UUID]
) -> None:
    foreign, department = provision(unit_engine)
    data = payload(requester)
    data["department_id"] = str(department)
    response = client.post("/requests", json=data, headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 422
    for field, value in (("status", "APPROVED"), ("organization_id", str(foreign.organization_id))):
        assert (
            client.post(
                "/requests",
                json={**payload(requester), field: value},
                headers={"Idempotency-Key": str(uuid4())},
            ).status_code
            == 422
        )
    assert client.post("/requests", json=payload(requester)).status_code == 422
    assert (
        client.post(
            "/requests", json=payload(requester), headers={"Idempotency-Key": "invalid"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("mutation", ["inactive", "revoked", "missing"])
def test_invalid_authenticated_requester(
    client: TestClient, unit_engine: Engine, requester: tuple[Principal, UUID], mutation: str
) -> None:
    if mutation == "missing":
        app.dependency_overrides[authenticated_principal] = lambda: Principal(
            requester[0].organization_id, uuid4()
        )
    else:
        from datetime import UTC, datetime

        with Session(unit_engine) as session, session.begin():
            if mutation == "inactive":
                user = session.get(User, requester[0].user_id)
                assert user is not None
                user.status = "inactive"
            else:
                role = session.get(
                    RoleAssignment,
                    (requester[0].organization_id, requester[0].user_id, Role.EMPLOYEE),
                )
                assert role is not None
                role.revoked_at = datetime.now(UTC)
    expected = 403 if mutation == "revoked" else 401
    assert (
        client.post(
            "/requests", json=payload(requester), headers={"Idempotency-Key": str(uuid4())}
        ).status_code
        == expected
    )
    assert client.get("/requests").status_code == expected


def test_schema_validation_and_minimal_state_model() -> None:
    for kind in RequestType:
        assert initial_request_status(kind) in {RequestStatus.DRAFT, RequestStatus.SUBMITTED}
    with pytest.raises(ValidationError):
        DepartmentCreate(name="   ")
    with pytest.raises(ValidationError):
        UserCreate(email="invalid", name="User", roles=frozenset({Role.EMPLOYEE}))
    with pytest.raises(ValidationError):
        UserCreate(email="user@example.invalid", name="User", roles=frozenset())
    data = payload((Principal(uuid4(), uuid4()), uuid4()))
    for field, value in (
        ("title", " "),
        ("raw_text", " "),
        ("status", "APPROVED"),
        ("organization_id", str(uuid4())),
        ("type", "unknown"),
    ):
        with pytest.raises(ValidationError):
            RequestCreate.model_validate({**data, field: value})
    assert "password_hash" not in UserRead.model_fields


def test_contract_describes_actual_error_media_type() -> None:
    paths = app.openapi()["paths"]
    for path in ("/requests", "/requests/{request_id}"):
        for operation in paths[path].values():
            for code in ("401", "403", "422"):
                assert set(operation["responses"][code]["content"]) == {"application/problem+json"}
