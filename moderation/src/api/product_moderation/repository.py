from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.blocking_reasons.domain import BlockingReasonDTO
from api.product_moderation.domain import (
    BlockResult,
    FieldReportInput,
    ModerationCard,
    TicketNotAssignedError,
    TicketNotFoundError,
    TicketWithoutSkuError,
    TicketWrongStatusError,
    UnknownBlockingReasonError,
    has_sku,
)
from models import BlockingReason, FieldReport, FieldReportSeverity, ProductModeration


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


# ---- Block (US-MOD-04 soft / US-MOD-05 hard) ----


class BlockRepositoryProtocol(Protocol):
    async def block(
        self,
        ticket_id: UUID,
        moderator_id: UUID,
        reason_ids: list[UUID],
        comment: str | None,
        field_reports: list[FieldReportInput],
    ) -> BlockResult:
        """Transition IN_REVIEW -> BLOCKED / HARD_BLOCKED for the assigned moderator.

        Block type is routed by the reasons' hard_block flag: any hard reason → hard.
        Raises TicketNotFoundError (404), TicketWrongStatusError (409),
        TicketNotAssignedError (409) or UnknownBlockingReasonError (400).
        """
        ...


def _check_ticket_for_block(card: ModerationCard, moderator_id: UUID) -> None:
    # Status before assignment — same ordering as approve.
    if card.status != "IN_REVIEW":
        raise TicketWrongStatusError
    if card.moderator_id != moderator_id:
        raise TicketNotAssignedError


def _resolve_reasons(
    reasons_by_id: dict[UUID, BlockingReasonDTO], reason_ids: list[UUID]
) -> tuple[bool, UUID, str]:
    """Validate every reason exists & is active; return (hard_block, primary_id, title)."""
    for reason_id in reason_ids:
        reason = reasons_by_id.get(reason_id)
        if reason is None or not reason.is_active:
            raise UnknownBlockingReasonError(str(reason_id))
    hard_block = any(reasons_by_id[rid].hard_block for rid in reason_ids)
    primary = reason_ids[0]
    return hard_block, primary, reasons_by_id[primary].title


def _blocked_card(
    card: ModerationCard, *, hard_block: bool, comment: str | None, now: datetime
) -> ModerationCard:
    return replace(
        card,
        status="HARD_BLOCKED" if hard_block else "BLOCKED",
        moderator_comment=comment if comment is not None else card.moderator_comment,
        date_moderation=now,
        date_updated=now,
    )


class InMemoryBlockRepository:
    """In-process repository for tests."""

    def __init__(self) -> None:
        self._cards: dict[UUID, ModerationCard] = {}
        self._reasons: dict[UUID, BlockingReasonDTO] = {}

    def seed_cards(self, *cards: ModerationCard) -> None:
        for c in cards:
            self._cards[c.id] = c

    def seed_reasons(self, *reasons: BlockingReasonDTO) -> None:
        for r in reasons:
            self._reasons[r.id] = r

    async def block(
        self,
        ticket_id: UUID,
        moderator_id: UUID,
        reason_ids: list[UUID],
        comment: str | None,
        field_reports: list[FieldReportInput],
    ) -> BlockResult:
        card = self._cards.get(ticket_id)
        if card is None:
            raise TicketNotFoundError
        _check_ticket_for_block(card, moderator_id)
        hard_block, primary_id, title = _resolve_reasons(self._reasons, reason_ids)
        blocked = _blocked_card(
            card, hard_block=hard_block, comment=comment, now=datetime.now(UTC)
        )
        self._cards[ticket_id] = blocked
        return BlockResult(
            card=blocked,
            hard_block=hard_block,
            blocking_reason_id=primary_id,
            blocking_reason_title=title,
            field_reports=tuple(field_reports),
        )


class DbBlockRepository:
    """Production repository backed by PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def block(
        self,
        ticket_id: UUID,
        moderator_id: UUID,
        reason_ids: list[UUID],
        comment: str | None,
        field_reports: list[FieldReportInput],
    ) -> BlockResult:
        now = datetime.now(UTC)
        pm = await self._session.scalar(
            select(ProductModeration).where(ProductModeration.id == ticket_id).with_for_update()
        )
        if pm is None:
            raise TicketNotFoundError
        _check_ticket_for_block(_pm_to_card(pm), moderator_id)

        rows = (
            await self._session.scalars(
                select(BlockingReason).where(BlockingReason.id.in_(reason_ids))
            )
        ).all()
        reasons_by_id = {
            row.id: BlockingReasonDTO(
                id=row.id,
                code=row.code,
                title=row.title,
                description=row.description,
                hard_block=bool(row.hard_block),
                is_active=bool(row.is_active),
            )
            for row in rows
        }
        hard_block, primary_id, title = _resolve_reasons(reasons_by_id, reason_ids)

        pm.status = "HARD_BLOCKED" if hard_block else "BLOCKED"
        pm.blocking_reason_id = primary_id
        pm.moderator_comment = comment
        pm.date_moderation = now
        pm.date_updated = now
        for fr in field_reports:
            self._session.add(
                FieldReport(
                    ticket_id=pm.id,
                    field_path=fr.field_path,
                    message=fr.message,
                    severity=FieldReportSeverity(fr.severity),
                )
            )
        await self._session.commit()
        return BlockResult(
            card=_blocked_card(_pm_to_card(pm), hard_block=hard_block, comment=comment, now=now),
            hard_block=hard_block,
            blocking_reason_id=primary_id,
            blocking_reason_title=title,
            field_reports=tuple(field_reports),
        )
