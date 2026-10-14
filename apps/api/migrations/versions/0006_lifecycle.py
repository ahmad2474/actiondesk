"""Approval reversal, immutable correction links and service work cycles."""

from pathlib import Path

from alembic import op

revision = "0006_lifecycle"
down_revision = "0005_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL requires a commit before newly added enum values can be used in guards.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE request_status_enum ADD VALUE IF NOT EXISTS 'REVERSAL_REVIEW'")
        op.execute("ALTER TYPE request_status_enum ADD VALUE IF NOT EXISTS 'REVERSED'")
    for statement in Path(__file__).with_suffix(".sql").read_text().split("-- statement-break"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    tables = [
        "request_reversal_requests",
        "request_reversal_decisions",
        "request_correction_links",
        "service_resolutions",
        "service_reopenings",
        "service_reopen_policies",
    ]
    conditions = " OR ".join(f"EXISTS (SELECT 1 FROM {table})" for table in tables)
    op.execute(f"""DO $$ BEGIN IF {conditions} OR EXISTS (SELECT 1 FROM requests
      WHERE active_reversal_id IS NOT NULL OR service_cycle_sequence IS NOT NULL
        OR latest_resolution_id IS NOT NULL OR status IN ('REVERSED','REVERSAL_REVIEW')) THEN
      RAISE EXCEPTION 'Lifecycle evidence must be preserved; downgrade blocked'; END IF; END $$;""")
    op.execute(
        "ALTER TABLE requests DROP CONSTRAINT fk_active_reversal, DROP CON"
        "STRAINT fk_latest_resolution, DROP CONSTRAINT fk_service_cycle"
    )
    for table in [
        "service_reopenings",
        "active_service_reopen_policies",
        "service_reopen_policies",
        "service_resolutions",
        "request_correction_links",
        "request_reversal_decisions",
        "request_reversal_requests",
    ]:
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP TRIGGER lifecycle_evidence_required ON requests")
    for function in [
        "guard_reversal_request",
        "guard_reversal_decision",
        "guard_correction_link",
        "guard_service_resolution",
        "guard_service_reopening",
        "require_lifecycle_evidence",
    ]:
        op.execute(f"DROP FUNCTION {function}()")
    op.execute("DROP FUNCTION lifecycle_final_candidate(UUID,UUID,UUID)")
    op.execute("DROP FUNCTION lifecycle_reversal_boundary(UUID,UUID,TIMESTAMPTZ)")
    op.execute(
        "ALTER TABLE requests DROP COLUMN active_reversal_id, DROP COLUMN "
        "service_cycle_sequence, DROP COLUMN latest_resolution_id"
    )
    op.execute("ALTER TABLE mutation_receipts DROP COLUMN related_request_id")
    op.execute("ALTER TABLE request_revisions DROP CONSTRAINT revision_kind")
    op.execute(
        "ALTER TABLE request_revisions ADD CONSTRAINT revision_kind CHECK("
        "kind IN ('submitted','captured','proposed'))"
    )
    original = Path(__file__).with_name("0005_revisions.sql").read_text()
    for statement in original.split("-- statement-break"):
        if statement.strip().startswith(("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")):
            op.execute(statement.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    # Enum labels are retained: PostgreSQL cannot safely remove them in-place.
