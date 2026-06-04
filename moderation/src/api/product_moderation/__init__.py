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
    FieldReportInput,
    ModerationCard,
    TicketNotAssignedError,
    TicketNotFoundError,
    TicketTerminalError,
    TicketWithoutSkuError,
    TicketWrongStatusError,
    UnknownBlockingReasonError,
)
from api.product_moderation.repository import (
    ApproveRepositoryProtocol,
    BlockRepositoryProtocol,
    DbApproveRepository,
    DbBlockRepository,
)
from auth import get_current_moderator_id
from database import AsyncSession, get_session
from modqueue.router import TicketResponse

_VALID_SEVERITIES = {"INFO", "WARNING", "ERROR"}

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


def get_block_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BlockRepositoryProtocol:
    return DbBlockRepository(session)


# ---- Stubs (other user stories) ----


@router.post("/product-moderation/get-next")
async def get_next_for_moderation() -> dict[str, str]:
    return {"endpoint": "get_next_for_moderation"}


# ---- Block (US-MOD-04 soft / US-MOD-05 hard) ----


class FieldReportPayload(BaseModel):
    # Per moderation/openapi.yaml FieldReport: field_path (JSONPath-like) + message + severity.
    field_path: str = Field(min_length=1)
    message: str = Field(max_length=1000)
    severity: str = "ERROR"


class BlockDecisionRequest(BaseModel):
    blocking_reason_ids: list[UUID] = Field(min_length=1)
    comment: str | None = Field(default=None, max_length=2000)
    field_reports: list[FieldReportPayload] = Field(default_factory=list)


@router.post("/tickets/{ticket_id}/block", response_model=None)
async def block_ticket(
    ticket_id: UUID,
    body: BlockDecisionRequest,
    moderator_id: Annotated[UUID, Depends(get_current_moderator_id)],
    repo: Annotated[BlockRepositoryProtocol, Depends(get_block_repo)],
    events: Annotated[B2BEventClientProtocol, Depends(get_b2b_event_client)],
) -> TicketResponse:
    """Block a ticket: IN_REVIEW -> BLOCKED (soft) or HARD_BLOCKED (hard).

    Block type is routed by the chosen reasons' hard_block flag (any hard → hard).
    Saves per-field reports, then emits a BLOCKED event (with hard_block) to B2B.
    """
    # severity is the only enum the spec constrains on a field report → validate to 400.
    for report in body.field_reports:
        if report.severity not in _VALID_SEVERITIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_REQUEST",
                    "message": f"Invalid severity '{report.severity}'",
                },
            )
    field_reports = [
        FieldReportInput(field_path=r.field_path, message=r.message, severity=r.severity)
        for r in body.field_reports
    ]

    try:
        result = await repo.block(
            ticket_id,
            moderator_id,
            reason_ids=body.blocking_reason_ids,
            comment=body.comment,
            field_reports=field_reports,
        )
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Ticket not found"},
        ) from exc
    except TicketTerminalError as exc:
        # HARD_BLOCKED is terminal — no mutation is allowed in the normal flow.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Ticket is hard-blocked (terminal)"},
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
    except UnknownBlockingReasonError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_REQUEST", "message": "Unknown or inactive blocking reason"},
        ) from exc

    await events.emit_blocked(
        product_id=result.card.product_id,
        hard_block=result.hard_block,
        blocking_reason_id=result.blocking_reason_id,
        blocking_reason_title=result.blocking_reason_title,
        moderator_comment=result.card.moderator_comment,
        # Map moderation field_reports → B2B shape (field_path → field_name, message → comment).
        field_reports=[
            {"field_name": fr.field_path, "comment": fr.message, "sku_id": None}
            for fr in result.field_reports
        ],
    )
    return _card_to_response(result.card)


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
    except TicketTerminalError as exc:
        # HARD_BLOCKED is terminal — no mutation is allowed in the normal flow.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Ticket is hard-blocked (terminal)"},
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
