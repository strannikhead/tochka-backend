"""B2B -> Moderation product events endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db import get_session
from models import (
    B2BEventType,
    FieldReport,
    ProcessedB2BEvent,
    ProductModeration,
    TicketKind,
    TicketStatus,
)

router = APIRouter(prefix="/api/v1/b2b/events", tags=["B2B Events"])

IDEMPOTENCY_TTL = timedelta(hours=24)


class IncomingB2BEvent(BaseModel):
    event_type: Literal["PRODUCT_CREATED", "PRODUCT_EDITED", "PRODUCT_DELETED"]
    idempotency_key: UUID
    occurred_at: datetime
    payload: dict[str, Any]


class EventProductCreated(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_id: UUID
    seller_id: UUID
    category_id: UUID | None = None
    queue_priority: int = Field(default=3, ge=1, le=4)
    json_after: dict[str, Any]


class EventProductEdited(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_id: UUID
    seller_id: UUID
    category_id: UUID | None = None
    queue_priority: int = Field(default=3, ge=1, le=4)
    json_before: dict[str, Any]
    json_after: dict[str, Any]


class EventProductDeleted(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_id: UUID


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _validate_service_key(x_service_key: str | None) -> None:
    settings = get_settings()
    if x_service_key != settings.b2b_to_mod_service_key:
        raise _error(status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED", "Невалидный X-Service-Key")


def _parse_payload(
    event: IncomingB2BEvent,
) -> EventProductCreated | EventProductEdited | EventProductDeleted:
    try:
        if event.event_type == B2BEventType.PRODUCT_CREATED.value:
            return EventProductCreated.model_validate(event.payload)
        if event.event_type == B2BEventType.PRODUCT_EDITED.value:
            return EventProductEdited.model_validate(event.payload)
        return EventProductDeleted.model_validate(event.payload)
    except ValidationError as exc:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "payload не соответствует event_type",
        ) from exc


async def _get_ticket_by_product_id(
    session: AsyncSession, product_id: UUID
) -> ProductModeration | None:
    result = await session.execute(
        select(ProductModeration).where(ProductModeration.product_id == product_id)
    )
    return result.scalar_one_or_none()


async def _clear_field_reports(session: AsyncSession, ticket_id: UUID) -> None:
    await session.execute(delete(FieldReport).where(FieldReport.ticket_id == ticket_id))


def _reset_ticket_for_queue(
    ticket: ProductModeration,
    *,
    seller_id: UUID,
    category_id: UUID | None,
    kind: TicketKind,
    queue_priority: int,
    json_before: dict[str, Any] | None,
    json_after: dict[str, Any],
) -> None:
    ticket.seller_id = seller_id
    ticket.category_id = category_id
    ticket.kind = kind.value
    ticket.status = TicketStatus.PENDING.value
    ticket.queue_priority = queue_priority
    ticket.moderator_id = None
    ticket.claimed_at = None
    ticket.claim_expires_at = None
    ticket.date_moderation = None
    ticket.moderator_comment = None
    ticket.json_before = json_before
    ticket.json_after = json_after
    ticket.date_updated = datetime.now(UTC)


async def _handle_created(session: AsyncSession, payload: EventProductCreated) -> None:
    ticket = await _get_ticket_by_product_id(session, payload.product_id)
    if ticket is None:
        session.add(
            ProductModeration(
                product_id=payload.product_id,
                seller_id=payload.seller_id,
                category_id=payload.category_id,
                kind=TicketKind.CREATE.value,
                status=TicketStatus.PENDING.value,
                queue_priority=payload.queue_priority,
                json_before=None,
                json_after=payload.json_after,
            )
        )
        return

    if ticket.status in {TicketStatus.HARD_BLOCKED, TicketStatus.HARD_BLOCKED.value}:
        return

    await _clear_field_reports(session, ticket.id)
    _reset_ticket_for_queue(
        ticket,
        seller_id=payload.seller_id,
        category_id=payload.category_id,
        kind=TicketKind.CREATE,
        queue_priority=payload.queue_priority,
        json_before=None,
        json_after=payload.json_after,
    )


async def _handle_edited(session: AsyncSession, payload: EventProductEdited) -> None:
    ticket = await _get_ticket_by_product_id(session, payload.product_id)
    if ticket is None:
        session.add(
            ProductModeration(
                product_id=payload.product_id,
                seller_id=payload.seller_id,
                category_id=payload.category_id,
                kind=TicketKind.EDIT.value,
                status=TicketStatus.PENDING.value,
                queue_priority=payload.queue_priority,
                json_before=payload.json_before,
                json_after=payload.json_after,
            )
        )
        return

    await _clear_field_reports(session, ticket.id)
    _reset_ticket_for_queue(
        ticket,
        seller_id=payload.seller_id,
        category_id=payload.category_id,
        kind=TicketKind.EDIT,
        queue_priority=payload.queue_priority,
        json_before=payload.json_before,
        json_after=payload.json_after,
    )


async def _handle_deleted(session: AsyncSession, payload: EventProductDeleted) -> None:
    ticket_ids_result = await session.execute(
        select(ProductModeration.id).where(ProductModeration.product_id == payload.product_id)
    )
    ticket_ids = list(ticket_ids_result.scalars().all())
    if ticket_ids:
        await session.execute(delete(FieldReport).where(FieldReport.ticket_id.in_(ticket_ids)))
    await session.execute(
        delete(ProductModeration).where(ProductModeration.product_id == payload.product_id)
    )


def _payload_product_id(
    payload: EventProductCreated | EventProductEdited | EventProductDeleted,
) -> UUID:
    return payload.product_id


async def _delete_expired_processed_events(session: AsyncSession) -> None:
    expires_before = datetime.now(UTC) - IDEMPOTENCY_TTL
    await session.execute(
        delete(ProcessedB2BEvent).where(ProcessedB2BEvent.processed_at < expires_before)
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_class=Response)
async def receive_b2b_event(
    event: IncomingB2BEvent,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_service_key: Annotated[str | None, Header(alias="X-Service-Key")] = None,
) -> Response:
    """Accept product events from B2B according to moderation/openapi.yaml."""

    _validate_service_key(x_service_key)
    payload = _parse_payload(event)

    try:
        async with session.begin():
            await _delete_expired_processed_events(session)

            existing_event = await session.scalar(
                select(ProcessedB2BEvent).where(
                    ProcessedB2BEvent.idempotency_key == event.idempotency_key
                )
            )
            if existing_event is not None:
                return Response(status_code=status.HTTP_409_CONFLICT)

            if event.event_type == B2BEventType.PRODUCT_CREATED.value:
                await _handle_created(session, payload)  # type: ignore[arg-type]
            elif event.event_type == B2BEventType.PRODUCT_EDITED.value:
                await _handle_edited(session, payload)  # type: ignore[arg-type]
            else:
                await _handle_deleted(session, payload)  # type: ignore[arg-type]

            session.add(
                ProcessedB2BEvent(
                    idempotency_key=event.idempotency_key,
                    event_type=B2BEventType(event.event_type),
                    product_id=_payload_product_id(payload),
                    occurred_at=event.occurred_at,
                )
            )
    except IntegrityError:
        await session.rollback()
        return Response(status_code=status.HTTP_409_CONFLICT)

    return Response(status_code=status.HTTP_202_ACCEPTED)
