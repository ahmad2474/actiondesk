"""Current tenant roles and snapshotted routing eligibility, shared by writes and reads."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ApprovalCandidate,
    DepartmentManager,
    EmployeeManager,
    Request,
    RoleAssignment,
    User,
)
from app.domain.identity import Principal
from app.domain.types import Role


def active_roles(session: Session, actor: Principal, *, lock: bool = False) -> frozenset[Role]:
    user_query = select(User).where(
        User.organization_id == actor.organization_id,
        User.id == actor.user_id,
        User.status == "active",
    )
    role_query = select(RoleAssignment).where(
        RoleAssignment.organization_id == actor.organization_id,
        RoleAssignment.user_id == actor.user_id,
        RoleAssignment.revoked_at.is_(None),
        RoleAssignment.granted_at <= datetime.now(UTC),
    )
    if lock:
        user_query = user_query.with_for_update(read=True)
        role_query = role_query.with_for_update(read=True)
    if session.scalar(user_query) is None:
        return frozenset()
    return frozenset(row.role for row in session.scalars(role_query))


def department_manager(
    session: Session, actor: Principal, department_id: UUID, *, lock: bool = False
) -> bool:
    if Role.MANAGER not in active_roles(session, actor, lock=lock):
        return False
    query = select(DepartmentManager).where(
        DepartmentManager.organization_id == actor.organization_id,
        DepartmentManager.department_id == department_id,
        DepartmentManager.manager_id == actor.user_id,
    )
    if lock:
        query = query.with_for_update(read=True)
    return session.scalar(query) is not None


def candidate_eligible(
    session: Session, record: Request, candidate: ApprovalCandidate, *, lock: bool = False
) -> bool:
    actor = Principal(record.organization_id, candidate.user_id)
    if candidate.user_id == record.created_by or candidate.required_role not in active_roles(
        session, actor, lock=lock
    ):
        return False
    if candidate.routing_source == "finance":
        return candidate.required_role == Role.FINANCE
    if candidate.required_role != Role.MANAGER:
        return False
    if candidate.routing_source == "employee_manager":
        query = select(EmployeeManager).where(
            EmployeeManager.organization_id == record.organization_id,
            EmployeeManager.employee_id == record.created_by,
            EmployeeManager.manager_id == candidate.user_id,
        )
        if lock:
            query = query.with_for_update(read=True)
        return session.scalar(query) is not None
    return candidate.routing_source == "department_manager" and department_manager(
        session, actor, record.department_id, lock=lock
    )
