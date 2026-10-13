"""Initial tenant-aware foundation; reviewed PostgreSQL DDL, no workflow engine."""

from pathlib import Path

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = Path(__file__).with_suffix(".sql").read_text().split("-- statement-break")
    for statement in statements:
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    # Destructive; never part of normal startup or seed commands.
    for table in [
        "outbox_events",
        "approvals",
        "request_events",
        "request_fields",
        "requests",
        "approval_policies",
        "department_managers",
        "employee_managers",
        "role_assignments",
        "users",
        "departments",
        "organizations",
    ]:
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_request_event_mutation()")
    for enum in ["request_status_enum", "request_type_enum", "role_enum"]:
        op.execute(f"DROP TYPE {enum}")
