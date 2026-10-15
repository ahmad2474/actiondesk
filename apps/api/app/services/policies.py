"""Resolve a complete approval plan from one explicitly selected immutable policy."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ActiveApprovalPolicy,
    Approval,
    ApprovalCandidate,
    ApprovalPolicy,
    DepartmentManager,
    EmployeeManager,
    Request,
    RoleAssignment,
)
from app.domain.errors import DomainError
from app.domain.identity import Principal
from app.domain.types import RequestType, Role
from app.schemas.workflow import ApprovalPolicyDefinition, ExpenseSubmission, Submission
from app.services.eligibility import active_roles, department_manager


@dataclass(frozen=True)
class PlannedStep:
    role: Role
    source: str
    candidates: tuple[UUID, ...]


def resolve_plan(
    session: Session, record: Request, data: Submission | None, *, lock: bool = True
) -> tuple[ApprovalPolicy, list[PlannedStep]]:
    selected_query = select(ActiveApprovalPolicy).where(
        ActiveApprovalPolicy.organization_id == record.organization_id,
        ActiveApprovalPolicy.request_type == record.type,
    )
    selected = session.scalar(selected_query.with_for_update(read=True) if lock else selected_query)
    if selected is None:
        raise DomainError(409, "Conflict", "No active approval policy is configured.")
    policy = session.scalar(
        select(ApprovalPolicy).where(
            ApprovalPolicy.organization_id == record.organization_id,
            ApprovalPolicy.id == selected.policy_id,
            ApprovalPolicy.request_type == record.type,
        )
    )
    assert policy is not None
    try:
        definition = ApprovalPolicyDefinition.model_validate(policy.definition)
    except ValidationError:
        raise DomainError(
            409, "Conflict", "The selected policy requires explicit validation."
        ) from None
    explicit_query = select(EmployeeManager).where(
        EmployeeManager.organization_id == record.organization_id,
        EmployeeManager.employee_id == record.created_by,
    )
    explicit = session.scalar(explicit_query.with_for_update(read=True) if lock else explicit_query)
    managers: tuple[UUID, ...] = ()
    source = "employee_manager"
    if explicit is not None and Role.MANAGER in active_roles(
        session, Principal(record.organization_id, explicit.manager_id), lock=lock
    ):
        managers = (explicit.manager_id,)
    elif definition.allow_department_fallback:
        source = "department_manager"
        manager_query = (
            select(DepartmentManager.manager_id)
            .where(
                DepartmentManager.organization_id == record.organization_id,
                DepartmentManager.department_id == record.department_id,
            )
            .order_by(DepartmentManager.manager_id)
        )
        ids = session.scalars(manager_query.with_for_update(read=True) if lock else manager_query)
        managers = tuple(
            user
            for user in ids
            if user != record.created_by
            and department_manager(
                session, Principal(record.organization_id, user), record.department_id, lock=lock
            )
        )
    if not managers:
        raise DomainError(409, "Conflict", "No valid manager approval candidate is available.")
    plan = [PlannedStep(Role.MANAGER, source, managers)]
    if record.type == RequestType.EXPENSE:
        if (
            definition.currency is None
            or definition.finance_threshold is None
            or (isinstance(data, ExpenseSubmission) and definition.currency != data.currency)
        ):
            raise DomainError(
                409, "Conflict", "Expense currency and finance threshold must be configured."
            )
        if isinstance(data, ExpenseSubmission) and data.amount > definition.finance_threshold:
            users = session.scalars(
                select(RoleAssignment.user_id)
                .where(
                    RoleAssignment.organization_id == record.organization_id,
                    RoleAssignment.role == Role.FINANCE,
                )
                .order_by(RoleAssignment.user_id)
            )
            candidates = tuple(
                user
                for user in users
                if user != record.created_by
                and Role.FINANCE
                in active_roles(session, Principal(record.organization_id, user), lock=lock)
            )
            if not candidates:
                raise DomainError(
                    409, "Conflict", "No valid finance approval candidate is available."
                )
            plan.append(PlannedStep(Role.FINANCE, "finance", candidates))
    elif definition.currency is not None or definition.finance_threshold is not None:
        raise DomainError(409, "Conflict", "Leave policy cannot contain expense thresholds.")
    return policy, plan


def persist_plan(session: Session, record: Request, plan: list[PlannedStep]) -> None:
    for position, step in enumerate(plan, start=1):
        approval = Approval(
            id=uuid4(),
            organization_id=record.organization_id,
            request_id=record.id,
            requester_id=record.created_by,
            step=position,
            submission_sequence=record.current_submission_sequence,
            approver_role=step.role,
            approver_id=None,
            status="pending",
        )
        session.add(approval)
        session.flush()
        session.add_all(
            ApprovalCandidate(
                organization_id=record.organization_id,
                approval_id=approval.id,
                request_id=record.id,
                requester_id=record.created_by,
                required_role=step.role,
                user_id=user,
                routing_source=step.source,
            )
            for user in step.candidates
        )
        session.flush()
