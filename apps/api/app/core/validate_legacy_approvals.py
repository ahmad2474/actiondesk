"""Explicit read-only local review of historical approval evidence."""

import argparse
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Request
from app.db.session import get_engine
from app.domain.types import RequestType
from app.services.legacy_plans import assess_legacy_plan


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate legacy approval evidence without changing it"
    )
    parser.add_argument("--organization-id", type=UUID, required=True)
    args = parser.parse_args()
    if get_settings().environment not in {"local", "test"}:
        raise RuntimeError("Explicit legacy review is local/test only")
    blocked = False
    with Session(get_engine()) as session:
        # SQLAlchemy transaction-level read-only protects against accidental future writes.
        from sqlalchemy import text

        session.execute(text("SET TRANSACTION READ ONLY"))
        records = session.scalars(
            select(Request)
            .where(
                Request.organization_id == args.organization_id,
                Request.type.in_([RequestType.EXPENSE, RequestType.LEAVE]),
                Request.workflow_version.is_(None),
            )
            .order_by(Request.id)
        )
        for record in records:
            assessment = assess_legacy_plan(session, record)
            print(
                json.dumps(
                    {"request_id": str(assessment.request_id), "blockers": assessment.blockers}
                )
            )
            blocked = blocked or bool(assessment.blockers)
    raise SystemExit(1 if blocked else 0)


if __name__ == "__main__":
    main()
