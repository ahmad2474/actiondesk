"""Deterministic, additive, local-only fixture loader; no business transitions."""

import argparse
from datetime import UTC, datetime
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, Table, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models
from app.db.session import get_engine
from app.domain.types import RequestStatus, RequestType, Role
from app.seed_fixtures import load_fixtures

SEED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def fixture_id(name: str) -> UUID:
    # Historical UUID namespace: keep stable when changing visible login identifiers.
    return uuid5(NAMESPACE_URL, f"https://actiondesk.invalid/seed/{name}")


def add(session: Session, table_name: str, values: dict[str, object]) -> None:
    table: Table = models.Base.metadata.tables[table_name]
    session.execute(insert(table).values(**values).on_conflict_do_nothing())


def seed(engine: Engine, count: Literal[10, 100] = 100) -> None:
    records = load_fixtures(count)  # Validate everything before opening the write transaction.
    org = fixture_id("organization")
    department = fixture_id("department")
    with Session(engine) as session, session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(41602000)"))
        add(
            session,
            "organizations",
            {
                "id": org,
                "slug": "synthetic-demo",
                "name": "Fictional ActionDesk Demo",
                "timezone": "Asia/Karachi",
                "created_at": SEED_AT,
            },
        )
        add(
            session,
            "departments",
            {"id": department, "organization_id": org, "name": "Demo Operations"},
        )
        for role in Role:
            user = fixture_id(f"user/{role.value}")
            add(
                session,
                "users",
                {
                    "id": user,
                    "organization_id": org,
                    "name": f"Fictional {role.value.title()}",
                    "email": f"{role.value}@actiondesk.ahmad",
                    "department_id": department,
                    "password_hash": None,
                    "status": "inactive",
                    "created_at": SEED_AT,
                },
            )
            for assigned_role in sorted({Role.EMPLOYEE, role}):
                add(
                    session,
                    "role_assignments",
                    {
                        "organization_id": org,
                        "user_id": user,
                        "role": assigned_role,
                        "granted_at": SEED_AT,
                    },
                )
        manager = fixture_id("user/manager")
        requester = fixture_id("user/employee")
        for role in (Role.EMPLOYEE, Role.FINANCE, Role.ADMIN):
            add(
                session,
                "employee_managers",
                {
                    "organization_id": org,
                    "employee_id": fixture_id(f"user/{role.value}"),
                    "manager_id": manager,
                },
            )
        add(
            session,
            "department_managers",
            {"organization_id": org, "department_id": department, "manager_id": manager},
        )
        for kind in (RequestType.EXPENSE, RequestType.LEAVE):
            definition: dict[str, object] = {
                "steps": [{"role": "manager", "scope": "employee_manager"}]
            }
            if kind == RequestType.EXPENSE:
                definition = {
                    "currency": "PKR",
                    "steps": [
                        {"role": "manager", "scope": "employee_manager", "amount_gt": "50000.00"},
                        {"role": "finance", "scope": "organization", "amount_gt": "200000.00"},
                    ],
                }
            add(
                session,
                "approval_policies",
                {
                    "id": fixture_id(f"policy/{kind}"),
                    "organization_id": org,
                    "name": f"demo-{kind}",
                    "version": 1,
                    "request_type": kind,
                    "definition": definition,
                },
            )
        for row in records:
            kind = RequestType(row.type)
            review = kind != RequestType.SERVICE
            status = RequestStatus.MANAGER_REVIEW if review else RequestStatus.SUBMITTED
            version = 2 if review else 1
            add(
                session,
                "requests",
                {
                    "id": row.id,
                    "organization_id": org,
                    "type": kind,
                    "title": row.title,
                    "raw_text": row.raw_text,
                    "status": status,
                    "created_by": requester,
                    "department_id": department,
                    "version": version,
                    "approval_policy_id": fixture_id(f"policy/{kind}") if review else None,
                    "created_at": row.created_at,
                    "updated_at": row.created_at,
                },
            )
            add(
                session,
                "request_fields",
                {
                    "organization_id": org,
                    "request_id": row.id,
                    "schema_version": 1,
                    "fields": row.fields.model_dump(mode="json"),
                },
            )
            for sequence in range(1, version + 1):
                event_state = RequestStatus.SUBMITTED if sequence == 1 else status
                add(
                    session,
                    "request_events",
                    {
                        "id": fixture_id(f"event/{row.id}/{sequence}"),
                        "organization_id": org,
                        "request_id": row.id,
                        "sequence": sequence,
                        "actor_id": requester if sequence == 1 else None,
                        "action": "seed_submitted" if sequence == 1 else "seed_review",
                        "from_state": None if sequence == 1 else RequestStatus.SUBMITTED,
                        "to_state": event_state,
                        "reason": "Synthetic historical fixture",
                        "at": row.created_at,
                    },
                )
            if review:
                add(
                    session,
                    "approvals",
                    {
                        "id": fixture_id(f"approval/{row.id}/1"),
                        "organization_id": org,
                        "request_id": row.id,
                        "requester_id": requester,
                        "step": 1,
                        "approver_id": manager,
                        "approver_role": Role.MANAGER,
                        "status": "pending",
                    },
                )
        # No outbox jobs: seeds are historical fixtures, not new actionable requests.


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load synthetic fixtures (additive; never resets data)"
    )
    parser.add_argument("--count", type=int, choices=(10, 100), default=100)
    args = parser.parse_args()
    if get_settings().environment not in ("local", "test"):
        raise RuntimeError("Synthetic seed is limited to local/test environments")
    count: Literal[10, 100] = 10 if args.count == 10 else 100
    seed(get_engine(), count)
    print(f"Synthetic seed verified: {count} requests; existing rows preserved.")


if __name__ == "__main__":
    main()
