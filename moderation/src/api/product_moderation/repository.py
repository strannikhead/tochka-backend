from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.product_moderation.domain import (
    ModerationCard,
    TicketNotAssignedError,
    TicketNotFoundError,
    TicketWithoutSkuError,
    TicketWrongStatusError,
    has_sku,
)
from models import ProductModeration


class ApproveRepositoryProtocol(Protocol):
    async def approve(
        self, ticket_id: UUID, moderator_id: UUID, comment: str | None
    ) -> ModerationCard:
        """Transition the ticket IN_REVIEW -> APPROVED for the assigned moderator.

        Raises TicketNotFoundError (404), TicketWrongStatusError (409),
        TicketNotAssignedError (409) or TicketWithoutSkuError (409).
        """
        ...


def _check_and_approve(
    card: ModerationCard, moderator_id: UUID, comment: str | None, now: datetime
) -> ModerationCard:
    """Pure precondition checks + transition, shared by both implementations.

    Order: status, assignment, SKU. Status is checked before assignment so an
    edited/re-queued ticket yields the status conflict regardless of its holder.
    """
    if card.status != "IN_REVIEW":
        raise TicketWrongStatusError
    if card.moderator_id != moderator_id:
        raise TicketNotAssignedError
    if not has_sku(card.json_after):
        raise TicketWithoutSkuError
    return replace(
        card,
        status="APPROVED",
        moderator_comment=comment if comment is not None else card.moderator_comment,
        date_moderation=now,
        date_updated=now,
    )


def _pm_to_card(pm: ProductModeration) -> ModerationCard:
    return ModerationCard(
        id=pm.id,
        product_id=pm.product_id,
        seller_id=pm.seller_id,
        category_id=pm.category_id,
        kind=pm.kind,
        status=pm.status,
        queue_priority=pm.queue_priority,
        moderator_id=pm.moderator_id,
        claimed_at=pm.claimed_at,
        claim_expires_at=pm.claim_expires_at,
        date_created=pm.date_created,
        date_updated=pm.date_updated,
        date_moderation=pm.date_moderation,
        moderator_comment=pm.moderator_comment,
        json_after=pm.json_after,
    )


class InMemoryApproveRepository:
    """In-process repository for tests, keyed by ticket id."""

    def __init__(self) -> None:
        self._cards: dict[UUID, ModerationCard] = {}

    def seed(self, *cards: ModerationCard) -> None:
        for c in cards:
            self._cards[c.id] = c

    def get(self, ticket_id: UUID) -> ModerationCard | None:
        return self._cards.get(ticket_id)

    async def approve(
        self, ticket_id: UUID, moderator_id: UUID, comment: str | None
    ) -> ModerationCard:
        card = self._cards.get(ticket_id)
        if card is None:
            raise TicketNotFoundError
        approved = _check_and_approve(card, moderator_id, comment, datetime.now(UTC))
        self._cards[ticket_id] = approved
        return approved


class DbApproveRepository:
    """Production repository backed by PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def approve(
        self, ticket_id: UUID, moderator_id: UUID, comment: str | None
    ) -> ModerationCard:
        now = datetime.now(UTC)
        pm = await self._session.scalar(
            select(ProductModeration).where(ProductModeration.id == ticket_id).with_for_update()
        )
        if pm is None:
            raise TicketNotFoundError

        approved = _check_and_approve(_pm_to_card(pm), moderator_id, comment, now)

        pm.status = approved.status
        pm.moderator_comment = approved.moderator_comment
        pm.blocking_reason_id = None
        pm.date_moderation = now
        pm.date_updated = now
        await self._session.commit()
        return approved
