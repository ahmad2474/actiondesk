"""Audited revisions and submission-scoped full reapproval."""

from pathlib import Path

from alembic import op

revision = "0005_revisions"
down_revision = "0004_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in Path(__file__).with_suffix(".sql").read_text().split("-- statement-break"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM request_revisions) OR EXISTS (SELECT 1 FROM request_submissions)
            OR EXISTS (SELECT 1 FROM request_change_requests)
            OR EXISTS (SELECT 1 FROM approvals WHERE submission_sequence IS NOT NULL)
            OR EXISTS (SELECT 1 FROM requests WHERE current_submission_sequence IS NOT NULL
              OR proposed_revision_id IS NOT NULL) THEN
            RAISE EXCEPTION 'Revision evidence must be preserved; downgrade blocked';
          END IF;
        END $$;
    """)
    op.execute(
        "ALTER TABLE requests DROP CONSTRAINT fk_current_submission, "
        "DROP CONSTRAINT fk_proposed_revision"
    )
    op.execute("DROP TABLE request_change_requests, request_submissions, request_revisions CASCADE")
    for name in ("guard_change_evidence", "guard_submission_evidence", "guard_revision_evidence"):
        op.execute(f"DROP FUNCTION {name}()")
    op.execute("DROP FUNCTION validate_revision_fields(request_type_enum, JSONB)")
    op.execute("DROP INDEX uq_approval_original_step")
    op.execute("ALTER TABLE approvals DROP COLUMN submission_sequence")
    op.execute("ALTER TABLE approvals ADD UNIQUE (organization_id,request_id,step)")
    op.execute(
        "ALTER TABLE requests DROP COLUMN current_submission_sequence, "
        "DROP COLUMN proposed_revision_id"
    )
    original = Path(__file__).with_name("0004_workflows.sql").read_text()
    for statement in original.split("-- statement-break"):
        if statement.strip().startswith("CREATE FUNCTION") and not statement.strip().startswith(
            "CREATE FUNCTION reject_workflow_evidence_mutation"
        ):
            op.execute(statement.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
