"""Real PostgreSQL migration, API and audit-boundary checks in disposable databases."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import authenticated_principal, database_session
from app.db.seed import fixture_id, seed
from app.domain.identity import Principal
from app.main import app

pytestmark = pytest.mark.integration


@pytest.fixture
def client(database: Engine) -> Iterator[TestClient]:
    seed(database, 10)
    with database.begin() as connection:
        connection.execute(
            text("UPDATE users SET status='active' WHERE id=:id"),
            {"id": fixture_id("user/employee")},
        )

    def session_override() -> Iterator[Session]:
        with Session(database) as session:
            yield session

    app.dependency_overrides[authenticated_principal] = lambda: Principal(
        fixture_id("organization"), fixture_id("user/employee")
    )
    app.dependency_overrides[database_session] = session_override
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def payload(kind: str = "service") -> dict[str, str]:
    return {
        "department_id": str(fixture_id("department")),
        "type": kind,
        "title": "Synthetic API request",
        "raw_text": "Synthetic integration fixture",
    }


@pytest.mark.parametrize(
    "kind,status", [("service", "SUBMITTED"), ("expense", "DRAFT"), ("leave", "DRAFT")]
)
def test_request_creation_history_retry_and_reads(
    client: TestClient, database: Engine, kind: str, status: str
) -> None:
    headers = {"Idempotency-Key": str(uuid4())}
    created = client.post("/requests", json=payload(kind), headers=headers)
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["status"] == status
    assert len(record["status_history"]) == 1
    assert record["status_history"][0]["from_state"] is None
    assert record["status_history"][0]["to_state"] == status
    assert record["status_history"][0]["actor_id"] == str(fixture_id("user/employee"))
    assert client.post("/requests", json=payload(kind), headers=headers).json() == record
    assert client.get(f"/requests/{record['id']}").json() == record
    assert client.get("/requests?limit=1").json()["items"][0]["id"] == record["id"]
    assert client.get(f"/requests/{uuid4()}").status_code == 404
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM requests")) == 11
        assert (
            connection.scalar(
                text("SELECT count(*) FROM request_events WHERE request_id=:id"),
                {"id": UUID(record["id"])},
            )
            == 1
        )
        assert connection.scalar(text("SELECT count(*) FROM outbox_events")) == 0


@pytest.mark.parametrize("field,status", [("requester_id", 422), ("department_id", 422)])
def test_invalid_references_leave_no_records(
    client: TestClient, database: Engine, field: str, status: int
) -> None:
    data = payload()
    data[field] = str(uuid4())
    result = client.post("/requests", json=data, headers={"Idempotency-Key": str(uuid4())})
    assert result.status_code == status
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM requests")) == 10


def test_creation_without_history_cannot_commit(database: Engine) -> None:
    seed(database, 10)
    with pytest.raises(IntegrityError) as error, database.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO requests(id,organization_id,type,title,raw_text,status,created_by,"
                "department_id) VALUES(:id,:org,'service','Synthetic','Synthetic','SUBMITTED',"
                ":user,:department)"
            ),
            {
                "id": uuid4(),
                "org": fixture_id("organization"),
                "user": fixture_id("user/employee"),
                "department": fixture_id("department"),
            },
        )
    assert getattr(error.value.orig, "sqlstate", None) == "23514"
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM requests")) == 10


@pytest.mark.parametrize(
    "mutation", ["status='TRIAGED'", "status='TRIAGED',version=version+1", "version=version+1"]
)
def test_unrecorded_state_or_version_change_cannot_commit(database: Engine, mutation: str) -> None:
    seed(database, 10)
    with pytest.raises(IntegrityError) as error, database.begin() as connection:
        connection.execute(text(f"UPDATE requests SET {mutation} WHERE type='service'"))
    assert getattr(error.value.orig, "sqlstate", None) == "23514"


def test_matching_history_satisfies_database_invariant(database: Engine) -> None:
    seed(database, 10)
    # Disposable DB probe only; no transition API or approval execution is introduced.
    with database.begin() as connection:
        request = connection.scalar(text("SELECT id FROM requests WHERE type='service' LIMIT 1"))
        connection.execute(
            text("UPDATE requests SET status='TRIAGED',version=2 WHERE id=:id"), {"id": request}
        )
        connection.execute(
            text(
                "INSERT INTO request_events(id,organization_id,request_id,sequence,actor_id,action,"
                "from_state,to_state,reason,at) VALUES(:id,:org,:request,2,:actor,'test_probe',"
                "'SUBMITTED','TRIAGED','Disposable constraint probe',now())"
            ),
            {
                "id": uuid4(),
                "org": fixture_id("organization"),
                "request": request,
                "actor": fixture_id("user/employee"),
            },
        )


def test_required_department_and_role_catalog(database: Engine) -> None:
    seed(database, 10)
    with database.connect() as connection:
        assert set(connection.scalars(text("SELECT name::text FROM roles"))) == {
            "employee",
            "manager",
            "finance",
            "admin",
        }
        assert (
            connection.scalar(
                text("SELECT count(*) FROM role_assignments WHERE user_id=:id"),
                {"id": fixture_id("user/manager")},
            )
            == 2
        )
    with pytest.raises(IntegrityError) as error, database.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO requests(id,organization_id,type,title,raw_text,status,created_by) "
                "VALUES(:id,:org,'service','Synthetic','Synthetic','SUBMITTED',:user)"
            ),
            {"id": uuid4(), "org": fixture_id("organization"), "user": fixture_id("user/employee")},
        )
    assert getattr(error.value.orig, "sqlstate", None) == "23502"


def test_existing_fixture_history_survives_migration_cycle(database: Engine) -> None:
    seed(database, 10)
    with database.connect() as connection:
        before = connection.execute(
            text("SELECT id,status,version,department_id FROM requests ORDER BY id")
        ).all()
        history_before = connection.execute(
            text("SELECT id,sequence,from_state,to_state FROM request_events ORDER BY id")
        ).all()
    configuration = Config("alembic.ini")
    command.downgrade(configuration, "0001_foundation")
    command.upgrade(configuration, "head")
    command.check(configuration)
    with database.connect() as connection:
        assert (
            connection.execute(
                text("SELECT id,status,version,department_id FROM requests ORDER BY id")
            ).all()
            == before
        )
        assert (
            connection.execute(
                text("SELECT id,sequence,from_state,to_state FROM request_events ORDER BY id")
            ).all()
            == history_before
        )
