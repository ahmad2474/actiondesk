"""Enriched, actor-scoped workflow queues; no global directory or workflow mutation."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.requests import Database, Identity, problem_response
from app.schemas.capabilities import QueueKind, WorkQueue
from app.services.capabilities import work_queue

router = APIRouter(
    prefix="/work-queues",
    tags=["Work queues"],
    responses={
        401: problem_response("Verified active identity required"),
        403: problem_response("Active organization role required"),
        409: problem_response("Organization display context requires validation"),
        422: problem_response("Invalid queue or pagination"),
    },
)


@router.get("/{queue}", response_model=WorkQueue, operation_id="get_work_queue")
def get_work_queue(
    queue: QueueKind,
    principal: Identity,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WorkQueue:
    return work_queue(session, principal, queue, limit, offset)
