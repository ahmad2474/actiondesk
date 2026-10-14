from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.dependencies import authenticated_principal, database_session
from app.domain.identity import Principal
from app.schemas.core import Problem, RequestCreate, RequestDetail, RequestPage
from app.services import requests


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
) -> RequestPage:
    return requests.list_requests(session, principal, limit, offset)
