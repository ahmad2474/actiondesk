"""Read-only legacy evidence assessment. Never fabricates or activates historical plans."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Approval,
    ApprovalCandidate,
    ApprovalDecision,
    ApprovalPolicy,
    Request,
    RequestFields,
)
from app.domain.types import RequestType
from app.schemas.workflow import ApprovalPolicyDefinition, ExpenseSubmission, LeaveSubmission


@dataclass(frozen=True)
class LegacyPlanAssessment:
    request_id: UUID
    blockers: tuple[str, ...]


def assess_legacy_plan(session: Session, record: Request) -> LegacyPlanAssessment:
    """Report evidence gaps without converting nominee/status into an actual decision."""
    blockers = ["Legacy provenance has no validated submission and routing snapshot"]
    fields = session.get(RequestFields, (record.organization_id, record.id))
    policy = session.scalar(
        select(ApprovalPolicy).where(
            ApprovalPolicy.organization_id == record.organization_id,
            ApprovalPolicy.id == record.approval_policy_id,
            ApprovalPolicy.request_type == record.type,
        )
    )
    try:
        if fields is None:
            raise ValueError("Missing fields")
        data = {**fields.fields, "type": record.type.value}
        if record.type == RequestType.EXPENSE:
            ExpenseSubmission.model_validate(data)
        else:
            LeaveSubmission.model_validate(data)
    except (ValidationError, ValueError):
        blockers.append("Authoritative fields require validation")
    try:
        if policy is None:
            raise ValueError("Missing policy")
        definition = ApprovalPolicyDefinition.model_validate(policy.definition)
        if record.type == RequestType.EXPENSE and definition.finance_threshold is None:
            raise ValueError("Missing expense threshold")
    except (ValidationError, ValueError):
        blockers.append("Historical policy does not establish the approved complete plan")
    steps = list(
        session.scalars(
            select(Approval)
            .where(
                Approval.organization_id == record.organization_id,
                Approval.request_id == record.id,
            )
            .order_by(Approval.step)
        )
    )
    if not steps:
        blockers.append("Approval steps are missing")
    for step in steps:
        if (
            session.scalar(
                select(ApprovalCandidate.user_id).where(
                    ApprovalCandidate.organization_id == record.organization_id,
                    ApprovalCandidate.approval_id == step.id,
                )
            )
            is None
        ):
            blockers.append(f"Step {step.step} has no historical candidate snapshot")
        if (
            step.status in {"approved", "rejected"}
            and session.scalar(
                select(ApprovalDecision.id).where(
                    ApprovalDecision.organization_id == record.organization_id,
                    ApprovalDecision.approval_id == step.id,
                )
            )
            is None
        ):
            blockers.append(f"Step {step.step} has no immutable actual-actor decision")
    return LegacyPlanAssessment(record.id, tuple(blockers))
