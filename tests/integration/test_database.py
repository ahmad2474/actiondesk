from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from redis import Redis
from sqlalchemy import Engine, UniqueConstraint, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import get_settings
from app.db.models import Base
from app.db.seed import SEED_AT, fixture_id, seed
from app.main import EXPECTED_REVISION, dependency_checks

pytestmark = pytest.mark.integration


def snapshot(engine: Engine) -> list[object]:
    result: list[object] = []
    with engine.connect() as connection:
        for table in [
            "roles",
            "organizations",
            "departments",
            "users",
            "role_assignments",
            "employee_managers",
            "department_managers",
            "approval_policies",
            "requests",
            "request_fields",
            "request_events",
            "approvals",
            "outbox_events",
        ]:
            rows = (
                connection.execute(
                    text(f"SELECT to_jsonb(t)::text FROM {table} AS t ORDER BY to_jsonb(t)::text")
                )
                .scalars()
                .all()
            )
            result.append((table, rows))
    return result


def test_seed_additive_idempotence_and_consistency(database: Engine) -> None:
    seed(database, 10)
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM requests")) == 10
    seed(database, 100)
    before = snapshot(database)
    seed(database, 100)
    seed(database, 10)
    assert snapshot(database) == before
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM requests")) == 100
        assert connection.scalar(text("SELECT count(*) FROM organizations")) == 1
        assert (
            connection.scalar(text("SELECT count(*) FROM users WHERE password_hash IS NOT NULL"))
            == 0
        )
        assert connection.scalar(text("SELECT count(*) FROM outbox_events")) == 0
        assert (
            connection.scalar(
                text("SELECT count(*) FROM role_assignments WHERE granted_at <> :fixed"),
                {"fixed": SEED_AT},
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM requests r WHERE NOT EXISTS "
                    "(SELECT 1 FROM request_events e WHERE e.request_id=r.id "
                    "AND e.sequence=r.version AND e.to_state=r.status)"
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM role_assignments WHERE user_id=:manager"),
                {"manager": fixture_id("user/manager")},
            )
            == 2
        )


def test_database_rejects_cross_organization_creator(database: Engine) -> None:
    seed(database)
    with database.connect() as connection, connection.begin():
        foreign_org = uuid4()
        foreign_department = uuid4()
        connection.execute(
            text("INSERT INTO organizations(id,slug,name) VALUES(:id,:slug,'Other')"),
            {"id": foreign_org, "slug": str(foreign_org)},
        )
        connection.execute(
            text("INSERT INTO departments(id,organization_id,name) VALUES(:id,:org,'Other')"),
            {"id": foreign_department, "org": foreign_org},
        )
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(
                text(
                    "INSERT INTO requests(id,organization_id,type,title,raw_text,status,"
                    "created_by,department_id) "
                    "VALUES(:id,:org,'service','Invalid','Synthetic','SUBMITTED',:creator,:department)"
                ),
                {
                    "id": uuid4(),
                    "org": foreign_org,
                    "creator": fixture_id("user/employee"),
                    "department": foreign_department,
                },
            )
        assert getattr(error.value.orig, "sqlstate", None) == "23503"


def test_manager_assignment_requires_manager_role(database: Engine) -> None:
    seed(database)
    with database.connect() as connection, connection.begin():
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "UPDATE employee_managers SET manager_id=:employee WHERE employee_id=:finance"
                ),
                {"employee": fixture_id("user/employee"), "finance": fixture_id("user/finance")},
            )


def test_self_approval_rejected_even_for_multi_role_user(database: Engine) -> None:
    seed(database)
    with database.connect() as connection, connection.begin():
        org, employee = fixture_id("organization"), fixture_id("user/employee")
        connection.execute(
            text(
                "INSERT INTO role_assignments(organization_id,user_id,role) "
                "VALUES(:org,:employee,'manager')"
            ),
            {"org": org, "employee": employee},
        )
        request_id = connection.scalar(text("SELECT id FROM requests WHERE type='expense' LIMIT 1"))
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text("UPDATE approvals SET approver_id=:employee WHERE request_id=:id"),
                {"employee": employee, "id": request_id},
            )
        # Roll back the temporary extra role without changing fixture roles.
        connection.rollback()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE request_events SET reason='modified'",
        "DELETE FROM request_events",
    ],
)
def test_request_events_append_only(database: Engine, statement: str) -> None:
    seed(database)
    with database.connect() as connection, connection.begin():
        with pytest.raises(DBAPIError, match="append-only"), connection.begin_nested():
            connection.execute(text(statement))


def test_live_readiness_and_redis(database: Engine) -> None:
    assert dependency_checks().model_dump() == {"database": "ok", "migrations": "ok", "redis": "ok"}
    with Redis.from_url(get_settings().redis_url, socket_timeout=2) as client:
        assert client.ping()
    with database.connect() as connection, connection.begin():
        connection.execute(text("UPDATE alembic_version SET version_num='not_head'"))
    assert dependency_checks().migrations == "unavailable"
    with database.connect() as connection, connection.begin():
        connection.execute(
            text("UPDATE alembic_version SET version_num=:head"), {"head": EXPECTED_REVISION}
        )


def test_expense_completion_requires_finance_attribution(database: Engine) -> None:
    seed(database)
    with database.connect() as connection, connection.begin():
        request_id = connection.scalar(text("SELECT id FROM requests WHERE type='expense' LIMIT 1"))
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text("UPDATE requests SET status='COMPLETED', completed_at=now() WHERE id=:id"),
                {"id": request_id},
            )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "UPDATE requests SET processed_by=:actor, processing_role='manager' "
                    "WHERE id=:id"
                ),
                {"id": request_id, "actor": fixture_id("user/manager")},
            )
        # No successful completion transition is implemented or invoked in Phase 0.


def test_minimal_seed_from_its_own_empty_database(database: Engine) -> None:
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM requests")) == 0
    seed(database, 10)
    first = snapshot(database)
    seed(database, 10)
    assert snapshot(database) == first
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM requests")) == 10
        assert connection.scalar(text("SELECT count(DISTINCT type) FROM requests")) == 3


def test_downgrade_upgrade_only_in_disposable_database(database: Engine) -> None:
    name = make_url(get_settings().database_url).database
    assert name is not None and name.startswith("actiondesk_test_")
    seed(database, 10)
    before = snapshot(database)
    configuration = Config("alembic.ini")
    command.downgrade(configuration, "base")
    assert set(inspect(database).get_table_names()) == {"alembic_version"}
    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 0
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_type WHERE typname IN "
                    "('role_enum','request_type_enum','request_status_enum')"
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM pg_proc WHERE proname='reject_request_event_mutation'")
            )
            == 0
        )
    command.upgrade(configuration, "head")
    command.check(configuration)
    seed(database, 10)
    assert snapshot(database) == before


def test_tables_relationships_unique_constraints_and_indexes(database: Engine) -> None:
    inspector = inspect(database)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    for name, table in Base.metadata.tables.items():
        assert {column["name"] for column in inspector.get_columns(name)} == set(
            table.columns.keys()
        )
        actual_fks = {
            (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
            for fk in inspector.get_foreign_keys(name)
        }
        expected_fks = {
            (
                tuple(fk.column_keys),
                fk.referred_table.name,
                tuple(element.column.name for element in fk.elements),
            )
            for fk in table.foreign_key_constraints
        }
        assert actual_fks == expected_fks
        actual_unique = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(name)
        }
        expected_unique = {
            tuple(constraint.columns.keys())
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert actual_unique == expected_unique
        actual_indexes = {index["name"] for index in inspector.get_indexes(name)}
        assert {index.name for index in table.indexes} <= actual_indexes
    assert {index["name"] for index in inspector.get_indexes("requests")} >= {
        "ix_requests_org_status_created",
        "ix_requests_org_assignee_status",
        "ix_requests_org_due",
    }


@pytest.mark.parametrize(
    "case",
    [
        "user_department",
        "role_user",
        "employee_manager",
        "department_manager",
        "request_creator",
        "request_assignee",
        "request_department",
        "request_policy",
        "request_follow_up",
        "request_processor",
        "request_fields",
        "event_request",
        "event_actor",
        "approval_request",
        "approval_actor",
        "outbox_request",
    ],
)
def test_tenant_relationships_reject_foreign_organization(database: Engine, case: str) -> None:
    seed(database)
    foreign_org, foreign_department, foreign_user, foreign_policy, foreign_request = [
        uuid4() for _ in range(5)
    ]
    org = fixture_id("organization")
    local_user = fixture_id("user/employee")
    with database.connect() as connection, connection.begin():
        connection.execute(
            text("INSERT INTO organizations(id,slug,name) VALUES(:id,:slug,'Other synthetic')"),
            {"id": foreign_org, "slug": str(foreign_org)},
        )
        connection.execute(
            text("INSERT INTO departments(id,organization_id,name) VALUES(:id,:org,'Other')"),
            {"id": foreign_department, "org": foreign_org},
        )
        connection.execute(
            text(
                "INSERT INTO users(id,organization_id,email,name) "
                "VALUES(:id,:org,'other@actiondesk.invalid','Other')"
            ),
            {"id": foreign_user, "org": foreign_org},
        )
        for role in ("manager", "finance"):
            connection.execute(
                text(
                    "INSERT INTO role_assignments(organization_id,user_id,role) "
                    "VALUES(:org,:id,:role)"
                ),
                {"org": foreign_org, "id": foreign_user, "role": role},
            )
        connection.execute(
            text(
                "INSERT INTO "
                "approval_policies(id,organization_id,name,version,request_type,definition)"
                " VALUES(:id,:org,'other-policy',1,'expense','{}')"
            ),
            {"id": foreign_policy, "org": foreign_org},
        )
        connection.execute(
            text(
                "INSERT INTO "
                "requests(id,organization_id,type,title,raw_text,status,created_by,department_id) "
                "VALUES(:id,:org,'expense','Other','Synthetic','SUBMITTED',:creator,:department)"
            ),
            {
                "id": foreign_request,
                "org": foreign_org,
                "creator": foreign_user,
                "department": foreign_department,
            },
        )
        connection.execute(
            text(
                "INSERT INTO request_events(id,organization_id,request_id,sequence,actor_id,"
                "action,to_state,reason,at) VALUES(:id,:org,:request,1,:actor,"
                "'created','SUBMITTED','Synthetic',now())"
            ),
            {"id": uuid4(), "org": foreign_org, "request": foreign_request, "actor": foreign_user},
        )
        local_request = connection.scalar(
            text("SELECT id FROM requests WHERE organization_id=:org AND type='expense' LIMIT 1"),
            {"org": org},
        )
        statements = {
            "user_department": (
                "UPDATE users SET department_id=:foreign_department WHERE id=:local_user"
            ),
            "role_user": (
                "INSERT INTO role_assignments(organization_id,user_id,role) "
                "VALUES(:org,:foreign_user,'employee')"
            ),
            "employee_manager": (
                "UPDATE employee_managers SET manager_id=:foreign_user WHERE "
                "employee_id=:local_user"
            ),
            "department_manager": (
                "UPDATE department_managers SET department_id=:foreign_department WHERE"
                " organization_id=:org"
            ),
            "request_creator": "UPDATE requests SET created_by=:foreign_user WHERE id=:request",
            "request_assignee": "UPDATE requests SET assigned_to=:foreign_user WHERE id=:request",
            "request_department": (
                "UPDATE requests SET department_id=:foreign_department WHERE id=:request"
            ),
            "request_policy": (
                "UPDATE requests SET approval_policy_id=:foreign_policy WHERE id=:request"
            ),
            "request_follow_up": (
                "UPDATE requests SET follow_up_to_id=:foreign_request WHERE id=:request"
            ),
            "request_processor": (
                "UPDATE requests SET processed_by=:foreign_user, "
                "processing_role='finance' WHERE id=:request"
            ),
            "request_fields": (
                "UPDATE request_fields SET request_id=:foreign_request WHERE request_id=:request"
            ),
            "event_request": (
                "INSERT INTO "
                "request_events(id,organization_id,request_id,sequence,action,to_state,reason,at)"
                " "
                "VALUES(:new_id,:org,:foreign_request,20,'probe','SUBMITTED','Synthetic',now())"
            ),
            "event_actor": (
                "INSERT INTO "
                "request_events(id,organization_id,request_id,sequence,actor_id,action,to_state,reason,at)"
                " "
                "VALUES(:new_id,:org,:request,20,:foreign_user,'probe','SUBMITTED','Synthetic',now())"
            ),
            "approval_request": (
                "UPDATE approvals SET request_id=:foreign_request, "
                "requester_id=:foreign_user WHERE request_id=:request"
            ),
            "approval_actor": (
                "UPDATE approvals SET approver_id=:foreign_user WHERE request_id=:request"
            ),
            "outbox_request": (
                "INSERT INTO "
                "outbox_events(id,organization_id,request_id,business_key,event_type,payload)"
                " VALUES(:new_id,:org,:foreign_request,'tenant-probe','probe','{}')"
            ),
        }
        parameters = {
            "org": org,
            "local_user": local_user,
            "request": local_request,
            "foreign_department": foreign_department,
            "foreign_user": foreign_user,
            "foreign_policy": foreign_policy,
            "foreign_request": foreign_request,
            "new_id": uuid4(),
        }
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(text(statements[case]), parameters)
        assert getattr(error.value.orig, "sqlstate", None) == "23503"  # Foreign-key violation.
