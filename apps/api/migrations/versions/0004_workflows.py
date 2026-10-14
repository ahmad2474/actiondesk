"""Manual workflows, immutable approval evidence and compact mutation receipts."""

from pathlib import Path

from alembic import op

revision = "0004_workflows"
down_revision = "0003_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in Path(__file__).with_suffix(".sql").read_text().split("-- statement-break"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    # Do not discard live decision evidence or turn managed requests into unvalidated legacy rows.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM requests WHERE workflow_version IS NOT NULL)
             OR EXISTS (SELECT 1 FROM approval_decisions)
             OR EXISTS (SELECT 1 FROM mutation_receipts) THEN
            RAISE EXCEPTION 'Workflow evidence must be preserved; downgrade blocked';
          END IF;
        END $$;
    """)
    for table, trigger in [
        ("requests", "workflow_request_guard"),
        ("requests", "workflow_evidence_required"),
        ("request_fields", "frozen_request_fields"),
        ("approval_policies", "immutable_approval_policies"),
        ("approval_candidates", "candidate_snapshot_guard"),
        ("approvals", "approval_plan_guard"),
        ("approvals", "approval_projection_guard"),
        ("approval_decisions", "decision_insert_guard"),
        ("approval_decisions", "immutable_approval_decisions"),
        ("mutation_receipts", "receipt_insert_guard"),
        ("mutation_receipts", "immutable_mutation_receipts"),
    ]:
        op.execute(f"DROP TRIGGER {trigger} ON {table}")
    for function in [
        "guard_workflow_request",
        "require_workflow_evidence",
        "guard_frozen_fields",
        "reject_workflow_evidence_mutation",
        "guard_candidate_snapshot",
        "guard_approval_plan",
        "guard_approval_projection",
        "guard_decision_insert",
        "guard_receipt_insert",
    ]:
        op.execute(f"DROP FUNCTION {function}()")
    op.execute("DROP FUNCTION workflow_candidate_eligible(UUID, UUID, UUID)")
    for table in [
        "mutation_receipts",
        "approval_decisions",
        "approval_candidates",
        "active_approval_policies",
    ]:
        op.drop_table(table)
    op.execute("ALTER TABLE approvals DROP CONSTRAINT approval_closed_event")
    op.execute("ALTER TABLE approvals DROP CONSTRAINT approval_identity")
    op.execute("ALTER TABLE approvals DROP COLUMN closed_event_sequence")
    op.execute("ALTER TABLE approvals DROP CONSTRAINT approval_status")
    op.execute(
        "ALTER TABLE approvals ADD CONSTRAINT approval_status "
        "CHECK (status IN ('pending','approved','rejected'))"
    )
    op.execute("ALTER TABLE approvals ALTER COLUMN approver_id SET NOT NULL")
    op.execute("ALTER TABLE approval_policies DROP CONSTRAINT policy_identity_type")
    for constraint in ["workflow_version", "submission_sequence", "no_self_processing"]:
        op.execute(f"ALTER TABLE requests DROP CONSTRAINT {constraint}")
    for column in [
        "workflow_version",
        "submission_sequence",
        "leave_overlap",
        "processing_reference",
        "resolution",
    ]:
        op.drop_column("requests", column)
