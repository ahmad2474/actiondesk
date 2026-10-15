"""Current tenant roles and snapshotted routing eligibility, shared by writes and reads."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import (
    ApprovalCandidate,
    Department,
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


def assignee_query(record: Request) -> Select[tuple[User]]:
    """Choices use exactly the tenant/department/active-role boundary used by assignment."""
    from sqlalchemy import exists

    return select(User).where(
        User.organization_id == record.organization_id,
        User.department_id == record.department_id,
        User.status == "active",
        exists(
            select(RoleAssignment.user_id).where(
                RoleAssignment.organization_id == User.organization_id,
                RoleAssignment.user_id == User.id,
                RoleAssignment.revoked_at.is_(None),
                RoleAssignment.granted_at <= datetime.now(UTC),
            )
        ),
    )


def require_assignee(
    session: Session, record: Request, user_id: UUID, *, lock: bool = True
) -> User:
    from app.domain.errors import DomainError

    query = assignee_query(record).where(User.id == user_id)
    user = session.scalar(query.with_for_update(read=True) if lock else query)
    if user is None or not active_roles(
        session, Principal(record.organization_id, user_id), lock=lock
    ):
        raise DomainError(
            422, "Unprocessable Content", "Assignee is unavailable in this department."
        )
    return user


def department_choices(actor: Principal) -> Select[tuple[Department]]:
    """The existing creation boundary: active principals may select a tenant department."""
    return select(Department).where(Department.organization_id == actor.organization_id)
