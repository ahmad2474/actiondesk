"""SQL predicates applied before pagination and before returning confidential objects."""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import (
    Approval,
    ApprovalCandidate,
    ApprovalDecision,
    DepartmentManager,
    EmployeeManager,
    Request,
    RequestChangeRequest,
    ReversalDecision,
    ReversalRequest,
    RoleAssignment,
)
from app.domain.errors import DomainError
from app.domain.identity import Principal
from app.domain.types import RequestStatus as S
from app.domain.types import RequestType as T
from app.domain.types import Role


class WorkScope(StrEnum):
    MINE = "mine"
    PARTICIPANT = "participant"
    ASSIGNED = "assigned"
    TRIAGE = "triage"
    PROCESSING = "processing"


def has_role(
    actor: Principal, role: Role | ColumnElement[Role] | InstrumentedAttribute[Role]
) -> ColumnElement[bool]:
    return exists(
        select(RoleAssignment.user_id).where(
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.user_id == actor.user_id,
            RoleAssignment.role == role,
            RoleAssignment.revoked_at.is_(None),
            RoleAssignment.granted_at <= datetime.now(UTC),
        )
    )


def manages_department(actor: Principal) -> ColumnElement[bool]:
    return and_(
        has_role(actor, Role.MANAGER),
        exists(
            select(DepartmentManager.manager_id).where(
                DepartmentManager.organization_id == Request.organization_id,
                DepartmentManager.department_id == Request.department_id,
                DepartmentManager.manager_id == actor.user_id,
            )
        ),
    )


def candidate_predicate(actor: Principal) -> ColumnElement[bool]:
    return and_(
        ApprovalCandidate.user_id == actor.user_id,
        ApprovalCandidate.organization_id == actor.organization_id,
        ApprovalCandidate.requester_id != actor.user_id,
        has_role(actor, ApprovalCandidate.required_role),
        or_(
            and_(
                ApprovalCandidate.routing_source == "finance",
                ApprovalCandidate.required_role == Role.FINANCE,
            ),
            and_(
                ApprovalCandidate.routing_source == "employee_manager",
                ApprovalCandidate.required_role == Role.MANAGER,
                exists(
                    select(EmployeeManager.manager_id).where(
                        EmployeeManager.organization_id == ApprovalCandidate.organization_id,
                        EmployeeManager.employee_id == ApprovalCandidate.requester_id,
                        EmployeeManager.manager_id == actor.user_id,
                    )
                ),
            ),
            and_(
                ApprovalCandidate.routing_source == "department_manager",
                ApprovalCandidate.required_role == Role.MANAGER,
                manages_department(actor),
            ),
        ),
    )


def processing_predicate(actor: Principal) -> ColumnElement[bool]:
    return and_(
        Request.type == T.EXPENSE,
        Request.workflow_version == 1,
        Request.status == S.APPROVED,
        Request.created_by != actor.user_id,
        has_role(actor, Role.FINANCE),
    )


def triage_predicate(actor: Principal) -> ColumnElement[bool]:
    return and_(
        Request.type == T.SERVICE,
        Request.status.in_([S.SUBMITTED, S.TRIAGED, S.ASSIGNED]),
        or_(has_role(actor, Role.ADMIN), manages_department(actor)),
    )


def current_approval() -> ColumnElement[bool]:
    return func.coalesce(
        Approval.submission_sequence, Request.submission_sequence
    ) == func.coalesce(Request.current_submission_sequence, Request.submission_sequence)


def visible_predicate(actor: Principal) -> ColumnElement[bool]:
    candidate = exists(
        select(ApprovalCandidate.user_id)
        .join(
            Approval,
            and_(
                Approval.organization_id == ApprovalCandidate.organization_id,
                Approval.id == ApprovalCandidate.approval_id,
            ),
        )
        .where(
            current_approval(),
            ApprovalCandidate.organization_id == Request.organization_id,
            ApprovalCandidate.request_id == Request.id,
            candidate_predicate(actor),
            Request.workflow_version == 1,
        )
    )
    decided = exists(
        select(ApprovalDecision.id).where(
            ApprovalDecision.organization_id == Request.organization_id,
            ApprovalDecision.request_id == Request.id,
            ApprovalDecision.actor_id == actor.user_id,
            has_role(actor, ApprovalDecision.required_role),
        )
    )
    service = and_(
        Request.type == T.SERVICE,
        or_(
            Request.assigned_to == actor.user_id,
            manages_department(actor),
            has_role(actor, Role.ADMIN),
        ),
    )
    return or_(
        Request.created_by == actor.user_id,
        service,
        candidate,
        decided,
        exists(
            select(RequestChangeRequest.event_sequence).where(
                RequestChangeRequest.organization_id == Request.organization_id,
                RequestChangeRequest.request_id == Request.id,
                RequestChangeRequest.actor_id == actor.user_id,
                has_role(actor, RequestChangeRequest.required_role),
            )
        ),
        exists(
            select(ReversalDecision.id)
            .join(
                ReversalRequest,
                (ReversalRequest.organization_id == ReversalDecision.organization_id)
                & (ReversalRequest.id == ReversalDecision.reversal_request_id),
            )
            .join(
                ApprovalDecision,
                (ApprovalDecision.organization_id == ReversalRequest.organization_id)
                & (ApprovalDecision.id == ReversalRequest.final_decision_id),
            )
            .where(
                ReversalDecision.organization_id == Request.organization_id,
                ReversalDecision.request_id == Request.id,
                ReversalDecision.actor_id == actor.user_id,
                has_role(actor, ApprovalDecision.required_role),
            )
        ),
        processing_predicate(actor),
        and_(
            Request.type == T.EXPENSE,
            Request.workflow_version == 1,
            Request.status == S.REVERSAL_REVIEW,
            Request.approved_at.is_not(None),
            Request.created_by != actor.user_id,
            has_role(actor, Role.FINANCE),
        ),
        and_(
            Request.type == T.EXPENSE,
            Request.processed_by == actor.user_id,
            has_role(actor, Role.FINANCE),
        ),
    )


def scoped_request(
    session: Session, actor: Principal, request_id: object, *, lock: bool = False
) -> Request:
    query = select(Request).where(
        Request.organization_id == actor.organization_id,
        Request.id == request_id,
        visible_predicate(actor),
    )
    if lock:
        query = query.with_for_update(of=Request)
    record = session.scalar(query)
    if record is None:
        raise DomainError(404, "Not Found", "Request not found.")
    return record


def actionable_approvals(actor: Principal) -> ColumnElement[bool]:
    earlier = Approval.__table__.alias("earlier")
    return and_(
        Request.organization_id == actor.organization_id,
        Request.workflow_version == 1,
        Approval.status == "pending",
        current_approval(),
        or_(
            and_(Request.status == S.MANAGER_REVIEW, Approval.approver_role == Role.MANAGER),
            and_(Request.status == S.FINANCE_REVIEW, Approval.approver_role == Role.FINANCE),
        ),
        ~exists(
            select(earlier.c.id).where(
                earlier.c.organization_id == Approval.organization_id,
                earlier.c.request_id == Approval.request_id,
                func.coalesce(earlier.c.submission_sequence, Request.submission_sequence)
                == func.coalesce(Request.current_submission_sequence, Request.submission_sequence),
                earlier.c.step < Approval.step,
                earlier.c.status != "approved",
            )
        ),
        exists(
            select(ApprovalCandidate.user_id).where(
                ApprovalCandidate.organization_id == Approval.organization_id,
                ApprovalCandidate.approval_id == Approval.id,
                candidate_predicate(actor),
            )
        ),
    )


def scope_predicate(actor: Principal, scope: WorkScope) -> ColumnElement[bool]:
    match scope:
        case WorkScope.MINE:
            return Request.created_by == actor.user_id
        case WorkScope.PARTICIPANT:
            return visible_predicate(actor)
        case WorkScope.ASSIGNED:
            return and_(
                Request.type == T.SERVICE,
                Request.assigned_to == actor.user_id,
                Request.status.in_([S.ASSIGNED, S.IN_PROGRESS, S.RESOLVED, S.REOPENED]),
            )
        case WorkScope.TRIAGE:
            return triage_predicate(actor)
        case WorkScope.PROCESSING:
            return processing_predicate(actor)


def reversal_predicate(actor: Principal) -> ColumnElement[bool]:
    """Current independent reversal nominations, correlated to the visible request."""
    decided = exists(
        select(ReversalDecision.id).where(
            ReversalDecision.organization_id == ReversalRequest.organization_id,
            ReversalDecision.reversal_request_id == ReversalRequest.id,
        )
    )
    return and_(
        Request.status == S.REVERSAL_REVIEW,
        exists(
            select(ReversalRequest.id)
            .join(
                ApprovalDecision,
                (ApprovalDecision.organization_id == ReversalRequest.organization_id)
                & (ApprovalDecision.id == ReversalRequest.final_decision_id),
            )
            .join(
                Approval,
                (Approval.organization_id == ApprovalDecision.organization_id)
                & (Approval.id == ApprovalDecision.approval_id),
            )
            .join(
                ApprovalCandidate,
                (ApprovalCandidate.organization_id == Approval.organization_id)
                & (ApprovalCandidate.approval_id == Approval.id),
            )
            .where(
                ReversalRequest.organization_id == Request.organization_id,
                ReversalRequest.request_id == Request.id,
                ReversalRequest.id == Request.active_reversal_id,
                current_approval(),
                ReversalRequest.actor_id != actor.user_id,
                candidate_predicate(actor),
                ~decided,
            )
            .correlate(Request)
        ),
    )
