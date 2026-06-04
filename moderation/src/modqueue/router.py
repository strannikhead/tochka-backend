from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from auth import get_current_moderator_id
from config import ApplicationSettings, get_settings
from database import AsyncSession, get_session
from modqueue.domain import Ticket
from modqueue.repository import DbQueueRepository, QueueRepositoryProtocol

router = APIRouter(prefix="/api/v1/queue", tags=["Queue"])


# ---- Pydantic schemas ----


class ClaimRequest(BaseModel):
    queue_priority: int | None = Field(None, ge=1, le=4)
    category_ids: list[UUID] | None = None


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    seller_id: UUID
    category_id: UUID | None = None
    kind: Literal["CREATE", "EDIT"]
    status: Literal["PENDING", "IN_REVIEW", "APPROVED", "BLOCKED", "HARD_BLOCKED"]
    queue_priority: int
    assigned_moderator_id: UUID | None = None
    claimed_at: datetime | None = None
    claim_expires_at: datetime | None = None
    decision_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


def _ticket_to_response(ticket: Ticket) -> TicketResponse:
    return TicketResponse(
        id=ticket.id,
        product_id=ticket.product_id,
        seller_id=ticket.seller_id,
        category_id=ticket.category_id,
        kind=ticket.kind,  # type: ignore[arg-type]
        status=ticket.status,  # type: ignore[arg-type]
        queue_priority=ticket.queue_priority,
        assigned_moderator_id=ticket.assigned_moderator_id,
        claimed_at=ticket.claimed_at,
        claim_expires_at=ticket.claim_expires_at,
        decision_at=ticket.decision_at,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


# ---- Dependency ----


def get_queue_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[ApplicationSettings, Depends(get_settings)],
) -> QueueRepositoryProtocol:
    return DbQueueRepository(session, cfg.review_timeout_minutes)


# ---- Endpoint ----


@router.post("/claim", response_model=None)
async def claim_next_ticket(
    moderator_id: Annotated[UUID, Depends(get_current_moderator_id)],
    repo: Annotated[QueueRepositoryProtocol, Depends(get_queue_repo)],
    cfg: Annotated[ApplicationSettings, Depends(get_settings)],
    body: ClaimRequest | None = None,
) -> TicketResponse | Response:
    """Atomically take the next PENDING ticket from the queue.

    Selects by queue_priority ASC then date_updated ASC (FIFO within priority).
    Uses SELECT FOR UPDATE SKIP LOCKED to prevent two moderators from claiming
    the same ticket under concurrent load.

    Returns 204 when the queue is empty.
    Returns 409 when the moderator already holds an active IN_REVIEW ticket.
    """
    ticket = await repo.claim_next(
        moderator_id=moderator_id,
        queue_priority=body.queue_priority if body else None,
        category_ids=body.category_ids if body else None,
        review_timeout_minutes=cfg.review_timeout_minutes,
    )

    if ticket is None:
        return Response(status_code=204)

    return _ticket_to_response(ticket)
