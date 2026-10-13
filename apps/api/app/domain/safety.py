"""Approved safety predicates only; not a workflow engine or authorization service."""

from datetime import date
from uuid import UUID

from app.domain.types import Role


def cancellation_is_safe(*, finally_approved: bool, irreversible_effect: bool) -> bool:
    return not finally_approved and not irreversible_effect


def approval_actor_is_separate(*, requester_id: UUID, approver_id: UUID) -> bool:
    return requester_id != approver_id


def expense_processing_role_is_eligible(roles: frozenset[Role]) -> bool:
    # Eligibility is necessary, not sufficient: object/state authorization arrives in Phase 1.
    return Role.FINANCE in roles


def leave_dates_are_ordered(start: date, end: date) -> bool:
    return start <= end
