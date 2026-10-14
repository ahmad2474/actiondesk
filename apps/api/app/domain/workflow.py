"""Milestone 3's deterministic forward-only workflow table."""

from enum import StrEnum

from app.domain.errors import DomainError
from app.domain.types import RequestStatus as S
from app.domain.types import RequestType as T


class Action(StrEnum):
    SUBMIT = "submit"
    ROUTE = "route"
    TRIAGE = "triage"
    ASSIGN = "assign"
    START = "start"
    RESOLVE = "resolve"
    CLOSE = "close"
    APPROVE = "approve"
    REJECT = "reject"
    PROCESS = "process"
    CANCEL = "cancel"


EDGES: dict[tuple[T, S, Action], frozenset[S]] = {
    (T.SERVICE, S.SUBMITTED, Action.TRIAGE): frozenset({S.TRIAGED}),
    (T.SERVICE, S.TRIAGED, Action.ASSIGN): frozenset({S.ASSIGNED}),
    (T.SERVICE, S.ASSIGNED, Action.START): frozenset({S.IN_PROGRESS}),
    (T.SERVICE, S.IN_PROGRESS, Action.RESOLVE): frozenset({S.RESOLVED}),
    (T.SERVICE, S.RESOLVED, Action.CLOSE): frozenset({S.CLOSED}),
    **{
        (T.SERVICE, state, Action.CANCEL): frozenset({S.CANCELLED})
        for state in (S.SUBMITTED, S.TRIAGED, S.ASSIGNED)
    },
    **{(kind, S.DRAFT, Action.SUBMIT): frozenset({S.SUBMITTED}) for kind in (T.EXPENSE, T.LEAVE)},
    **{
        (kind, S.SUBMITTED, Action.ROUTE): frozenset({S.MANAGER_REVIEW})
        for kind in (T.EXPENSE, T.LEAVE)
    },
    (T.EXPENSE, S.MANAGER_REVIEW, Action.APPROVE): frozenset({S.FINANCE_REVIEW, S.APPROVED}),
    (T.EXPENSE, S.FINANCE_REVIEW, Action.APPROVE): frozenset({S.APPROVED}),
    (T.LEAVE, S.MANAGER_REVIEW, Action.APPROVE): frozenset({S.APPROVED}),
    **{
        (kind, state, Action.REJECT): frozenset({S.REJECTED})
        for kind, states in (
            (T.EXPENSE, (S.MANAGER_REVIEW, S.FINANCE_REVIEW)),
            (T.LEAVE, (S.MANAGER_REVIEW,)),
        )
        for state in states
    },
    (T.EXPENSE, S.APPROVED, Action.PROCESS): frozenset({S.COMPLETED}),
    **{
        (kind, state, Action.CANCEL): frozenset({S.WITHDRAWN})
        for kind, states in (
            (T.EXPENSE, (S.DRAFT, S.SUBMITTED, S.MANAGER_REVIEW, S.FINANCE_REVIEW)),
            (T.LEAVE, (S.DRAFT, S.SUBMITTED, S.MANAGER_REVIEW)),
        )
        for state in states
    },
}


def require_edge(kind: T, source: S, action: Action, target: S) -> None:
    if target not in EDGES.get((kind, source, action), frozenset()):
        raise DomainError(409, "Conflict", "Action is not allowed in the current state.")
