"""Deterministic workflows with explicit audited revision/reversal/work cycles."""

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
    REQUEST_CHANGES = "request_changes"
    REVISE = "revise"
    RESUBMIT = "resubmit"
    REQUEST_REVERSAL = "request_reversal"
    APPROVE_REVERSAL = "approve_reversal"
    REJECT_REVERSAL = "reject_reversal"
    CREATE_CORRECTION = "create_correction"
    REOPEN = "reopen"


EDGES: dict[tuple[T, S, Action], frozenset[S]] = {
    **{
        (kind, source, action): frozenset({target})
        for kind in (T.EXPENSE, T.LEAVE)
        for source, action, target in (
            (S.APPROVED, Action.REQUEST_REVERSAL, S.REVERSAL_REVIEW),
            (S.REVERSAL_REVIEW, Action.APPROVE_REVERSAL, S.REVERSED),
            (S.REVERSAL_REVIEW, Action.REJECT_REVERSAL, S.APPROVED),
            (S.REVERSED, Action.CREATE_CORRECTION, S.REVERSED),
        )
    },
    (T.SERVICE, S.RESOLVED, Action.REOPEN): frozenset({S.REOPENED}),
    (T.SERVICE, S.REOPENED, Action.START): frozenset({S.IN_PROGRESS}),
    **{
        (kind, state, Action.REQUEST_CHANGES): frozenset({S.NEEDS_INFO})
        for kind, states in (
            (T.EXPENSE, (S.MANAGER_REVIEW, S.FINANCE_REVIEW)),
            (T.LEAVE, (S.MANAGER_REVIEW,)),
        )
        for state in states
    },
    **{
        (kind, S.NEEDS_INFO, action): frozenset({target})
        for kind in (T.EXPENSE, T.LEAVE)
        for action, target in (
            (Action.REVISE, S.NEEDS_INFO),
            (Action.RESUBMIT, S.SUBMITTED),
            (Action.CANCEL, S.WITHDRAWN),
        )
    },
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
