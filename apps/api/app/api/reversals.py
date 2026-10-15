"""Independent current-candidate reversal work queue."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.requests import Database, Identity, problem_response
from app.db.models import Request, ReversalRequest
from app.schemas.core import ReversalPage, ReversalRequestRead
from app.services.requests import validate_principal
from app.services.visibility import reversal_predicate

router = APIRouter(
    prefix="/reversals",
    tags=["Reversals"],
    responses={
        401: problem_response("Verified active identity required"),
        403: problem_response("Active organization role required"),
        422: problem_response("Invalid pagination"),
    },
)


@router.get("", response_model=ReversalPage, operation_id="list_reversals")
def list_reversals(
    principal: Identity,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReversalPage:
    validate_principal(session, principal)
    query = (
        select(ReversalRequest)
        .join(
            Request,
            (Request.organization_id == ReversalRequest.organization_id)
            & (Request.id == ReversalRequest.request_id),
        )
        .where(
            Request.organization_id == principal.organization_id,
            ReversalRequest.id == Request.active_reversal_id,
            reversal_predicate(principal),
        )
        .order_by(ReversalRequest.event_sequence, ReversalRequest.id)
        .limit(limit)
        .offset(offset)
    )
    return ReversalPage(
        items=[ReversalRequestRead.model_validate(item) for item in session.scalars(query)],
        limit=limit,
        offset=offset,
    )
