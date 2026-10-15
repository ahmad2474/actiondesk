from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.dependencies import authenticated_principal, database_session
from app.domain.identity import Principal
from app.schemas.capabilities import CreationOptions, RequestCapabilities
from app.schemas.core import (
    LifecyclePage,
    Problem,
    RequestCreate,
    RequestDetail,
    RequestPage,
    RevisionPage,
)
from app.schemas.workflow import Transition, TransitionRead
from app.services import capabilities, requests, transition_service
from app.services.visibility import WorkScope


def problem_response(description: str) -> dict[str, object]:
    return {
        "description": description,
        "content": {"application/problem+json": {"schema": Problem.model_json_schema()}},
    }


router = APIRouter(
    prefix="/requests",
    tags=["Requests"],
    responses={
        401: problem_response("Verified active identity required"),
        403: problem_response("Requester or role restriction"),
        422: problem_response("Invalid input or unavailable department"),
    },
)
Identity = Annotated[Principal, Depends(authenticated_principal)]
Database = Annotated[Session, Depends(database_session)]


@router.post(
    "",
    response_model=RequestDetail,
    status_code=201,
    operation_id="create_request",
    responses={409: problem_response("Conflicting creation retry")},
)
def create_request(
    payload: RequestCreate,
    principal: Identity,
    session: Database,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> RequestDetail:
    return requests.create_request(session, principal, payload, idempotency_key)


@router.get(
    "/options",
    response_model=CreationOptions,
    operation_id="get_request_options",
    responses={409: problem_response("Organization display context requires validation")},
)
def get_request_options(
    principal: Identity,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CreationOptions:
    return capabilities.creation_options(session, principal, limit, offset)


@router.get(
    "/{request_id}",
    response_model=RequestDetail,
    operation_id="get_request",
    responses={404: problem_response("Request missing or not visible")},
)
def get_request(request_id: UUID, principal: Identity, session: Database) -> RequestDetail:
    return requests.get_request(session, principal, request_id)


@router.get("", response_model=RequestPage, operation_id="list_requests")
def list_requests(
    principal: Identity,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    scope: WorkScope = WorkScope.MINE,
) -> RequestPage:
    return requests.list_requests(session, principal, limit, offset, scope)


@router.post(
    "/{request_id}/transitions",
    response_model=TransitionRead,
    operation_id="transition_request",
    description="Typed action. Idempotency-Key binds actor, request and canonical payload. "
    "Exact retries return the original compact outcome and currently authorized detail.",
    responses={
        404: problem_response("Request missing or not visible"),
        409: problem_response("Invalid edge, stale version, blocked plan or conflicting retry"),
    },
)
def transition_request(
    request_id: UUID,
    payload: Transition,
    principal: Identity,
    session: Database,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> TransitionRead:
    return transition_service.transition(
        session, principal, request_id, payload, payload.expected_version, idempotency_key
    )


@router.get(
    "/{request_id}/revisions",
    response_model=RevisionPage,
    operation_id="list_request_revisions",
    responses={404: problem_response("Request missing or not visible")},
)
def list_request_revisions(
    request_id: UUID,
    principal: Identity,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RevisionPage:
    return requests.list_revisions(session, principal, request_id, limit, offset)


@router.get(
    "/{request_id}/lifecycle",
    response_model=LifecyclePage,
    operation_id="list_request_lifecycle",
    responses={404: problem_response("Request missing or not visible")},
)
def list_request_lifecycle(
    request_id: UUID,
    principal: Identity,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LifecyclePage:
    return requests.list_lifecycle(session, principal, request_id, limit, offset)


@router.get(
    "/{request_id}/capabilities",
    response_model=RequestCapabilities,
    operation_id="get_request_capabilities",
    description="Read-only current Principal capabilities. "
    "Advisory snapshot bound to expected_version; "
    "typed mutations recheck all authority under lock. Form input is still required.",
    responses={
        404: problem_response("Request missing or not visible"),
        409: problem_response("Organization display context requires validation"),
    },
)
def get_request_capabilities(
    request_id: UUID,
    principal: Identity,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RequestCapabilities:
    return capabilities.get_capabilities(session, principal, request_id, limit, offset)
