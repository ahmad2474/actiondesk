"""SQL predicates applied before pagination and before returning confidential objects."""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import (
    Approval,
    ApprovalCandidate,
    ApprovalDecision,
    DepartmentManager,
    EmployeeManager,
    Request,
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


def visible_predicate(actor: Principal) -> ColumnElement[bool]:
    candidate = exists(
        select(ApprovalCandidate.user_id).where(
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
        processing_predicate(actor),
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
        or_(
            and_(Request.status == S.MANAGER_REVIEW, Approval.approver_role == Role.MANAGER),
            and_(Request.status == S.FINANCE_REVIEW, Approval.approver_role == Role.FINANCE),
        ),
        ~exists(
            select(earlier.c.id).where(
                earlier.c.organization_id == Approval.organization_id,
                earlier.c.request_id == Approval.request_id,
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
                Request.status.in_([S.ASSIGNED, S.IN_PROGRESS, S.RESOLVED]),
            )
        case WorkScope.TRIAGE:
            return triage_predicate(actor)
        case WorkScope.PROCESSING:
            return processing_predicate(actor)
