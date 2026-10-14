from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.requests import Database, Identity, problem_response
from app.db.models import Approval, Request
from app.schemas.workflow import ApprovalPage, ApprovalRead
from app.services.requests import validate_principal
from app.services.visibility import actionable_approvals

router = APIRouter(
    prefix="/approvals",
    tags=["Approvals"],
    responses={
        401: problem_response("Verified active identity required"),
        403: problem_response("Active organization role required"),
        422: problem_response("Invalid pagination"),
    },
)


@router.get("", response_model=ApprovalPage, operation_id="list_approvals")
def list_approvals(
    principal: Identity,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApprovalPage:
    validate_principal(session, principal)
    steps = session.scalars(
        select(Approval)
        .join(
            Request,
            (
                (Request.organization_id == Approval.organization_id)
                & (Request.id == Approval.request_id)
            ),
        )
        .where(actionable_approvals(principal))
        .order_by(Request.created_at, Request.id, Approval.step)
        .limit(limit)
        .offset(offset)
    )
    return ApprovalPage(
        items=[ApprovalRead.model_validate(step) for step in steps], limit=limit, offset=offset
    )
