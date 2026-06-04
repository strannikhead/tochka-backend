from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.product_moderation.b2b_client import (
    B2BEventClientProtocol,
    HttpB2BEventClient,
)
from api.product_moderation.domain import (
    ModerationCard,
    TicketNotAssignedError,
    TicketNotFoundError,
    TicketWithoutSkuError,
    TicketWrongStatusError,
)
from api.product_moderation.repository import (
    ApproveRepositoryProtocol,
    DbApproveRepository,
)
from auth import get_current_moderator_id
from database import AsyncSession, get_session
from modqueue.router import TicketResponse

router = APIRouter(prefix="/api/v1", tags=["product-moderation"])


# ---- Schemas ----


class ApproveRequest(BaseModel):
    comment: str | None = Field(None, max_length=2000)


def _card_to_response(card: ModerationCard) -> TicketResponse:
    return TicketResponse(
        id=card.id,
        product_id=card.product_id,
        seller_id=card.seller_id,
        category_id=card.category_id,
        kind=card.kind,  # type: ignore[arg-type]
        status=card.status,  # type: ignore[arg-type]
        queue_priority=card.queue_priority,
        assigned_moderator_id=card.moderator_id,
        claimed_at=card.claimed_at,
        claim_expires_at=card.claim_expires_at,
        decision_at=card.date_moderation,
        created_at=card.date_created,
        updated_at=card.date_updated,
    )


# ---- Dependencies ----


def get_approve_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApproveRepositoryProtocol:
    return DbApproveRepository(session)


def get_b2b_event_client() -> B2BEventClientProtocol:
    return HttpB2BEventClient()


# ---- Stubs (other user stories) ----


@router.post("/product-moderation/get-next")
async def get_next_for_moderation() -> dict[str, str]:
    return {"endpoint": "get_next_for_moderation"}


@router.post("/products/{id}/decline")
async def decline_product(id: str) -> dict[str, str]:
    return {"endpoint": "decline_product"}


# ---- Approve (US-MOD-03) ----


@router.post("/tickets/{ticket_id}/approve", response_model=None)
async def approve_ticket(
    ticket_id: UUID,
    moderator_id: Annotated[UUID, Depends(get_current_moderator_id)],
    repo: Annotated[ApproveRepositoryProtocol, Depends(get_approve_repo)],
    events: Annotated[B2BEventClientProtocol, Depends(get_b2b_event_client)],
    body: ApproveRequest | None = None,
) -> TicketResponse:
    """Approve a ticket: IN_REVIEW -> APPROVED, then emit a MODERATED event to B2B.

    Preconditions: the ticket exists, is IN_REVIEW, belongs to the calling
    moderator and the product has at least one SKU. The status transition is the
    idempotency guard — a second approve hits the 409 status check and never
    re-emits, so the catalog cannot be double-published.
    """
    try:
        card = await repo.approve(
            ticket_id,
            moderator_id,
            comment=body.comment if body else None,
        )
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Ticket not found"},
        ) from exc
    except TicketWrongStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TICKET_WRONG_STATUS", "message": "Ticket is not in review status"},
        ) from exc
    except TicketNotAssignedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TICKET_NOT_ASSIGNED",
                "message": "Ticket is assigned to another moderator",
            },
        ) from exc
    except TicketWithoutSkuError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TICKET_WITHOUT_SKU", "message": "Product has no SKUs, cannot approve"},
        ) from exc

    await events.emit_moderated(card.product_id)
    return _card_to_response(card)
