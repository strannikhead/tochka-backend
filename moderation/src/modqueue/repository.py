from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import ProductModeration
from modqueue.domain import ModeratorAlreadyInReviewError, Ticket


class QueueRepositoryProtocol(Protocol):
    async def claim_next(
        self,
        moderator_id: UUID,
        queue_priority: int | None,
        category_ids: list[UUID] | None,
        review_timeout_minutes: int,
    ) -> Ticket | None:
        """Atomically claim the next PENDING ticket.

        Raises ModeratorAlreadyInReviewError if the moderator already holds
        a non-expired IN_REVIEW ticket.
        Returns None when the queue is empty.
        """
        ...


def _pm_to_ticket(pm: ProductModeration) -> Ticket:
    return Ticket(
        id=pm.id,
        product_id=pm.product_id,
        seller_id=pm.seller_id,
        category_id=pm.category_id,
        kind=pm.kind,
        status=pm.status,
        queue_priority=pm.queue_priority,
        assigned_moderator_id=pm.moderator_id,
        claimed_at=pm.claimed_at,
        claim_expires_at=pm.claim_expires_at,
        decision_at=pm.date_moderation,
        created_at=pm.date_created,
        updated_at=pm.date_updated,
    )


class InMemoryQueueRepository:
    """In-process repository for tests — mimics SELECT FOR UPDATE SKIP LOCKED via asyncio.Lock."""

    def __init__(self) -> None:
        self._tickets: dict[UUID, Ticket] = {}
        self._lock = asyncio.Lock()

    def seed(self, *tickets: Ticket) -> None:
        for t in tickets:
            self._tickets[t.id] = t

    async def claim_next(
        self,
        moderator_id: UUID,
        queue_priority: int | None,
        category_ids: list[UUID] | None,
        review_timeout_minutes: int,
    ) -> Ticket | None:
        async with self._lock:
            now = datetime.now(UTC)

            # Reset expired IN_REVIEW tickets back to PENDING
            for tid, t in list(self._tickets.items()):
                if (
                    t.status == "IN_REVIEW"
                    and t.claim_expires_at is not None
                    and t.claim_expires_at <= now
                ):
                    self._tickets[tid] = replace(
                        t,
                        status="PENDING",
                        assigned_moderator_id=None,
                        claimed_at=None,
                        claim_expires_at=None,
                        updated_at=now,
                    )

            # Reject if moderator already holds an active IN_REVIEW ticket
            for t in self._tickets.values():
                if t.status == "IN_REVIEW" and t.assigned_moderator_id == moderator_id:
                    raise ModeratorAlreadyInReviewError

            priorities = [queue_priority] if queue_priority is not None else [1, 2, 3, 4]

            for priority in priorities:
                candidates = [
                    t
                    for t in self._tickets.values()
                    if t.status == "PENDING"
                    and t.queue_priority == priority
                    and (category_ids is None or t.category_id in category_ids)
                ]
                if not candidates:
                    continue

                candidates.sort(key=lambda t: t.updated_at or t.created_at)
                ticket = candidates[0]

                claimed_at = now
                expires_at = now + timedelta(minutes=review_timeout_minutes)
                claimed = replace(
                    ticket,
                    status="IN_REVIEW",
                    assigned_moderator_id=moderator_id,
                    claimed_at=claimed_at,
                    claim_expires_at=expires_at,
                    updated_at=now,
                )
                self._tickets[ticket.id] = claimed
                return claimed

            return None


class DbQueueRepository:
    """Production repository using SELECT FOR UPDATE SKIP LOCKED."""

    def __init__(self, session: AsyncSession, review_timeout_minutes: int) -> None:
        self._session = session
        self._review_timeout_minutes = review_timeout_minutes

    async def claim_next(
        self,
        moderator_id: UUID,
        queue_priority: int | None,
        category_ids: list[UUID] | None,
        review_timeout_minutes: int,
    ) -> Ticket | None:
        now = datetime.now(UTC)

        # Reset expired IN_REVIEW tickets in the same transaction
        await self._session.execute(
            update(ProductModeration)
            .where(
                ProductModeration.status == "IN_REVIEW",
                ProductModeration.claim_expires_at <= now,
            )
            .values(
                status="PENDING",
                moderator_id=None,
                claimed_at=None,
                claim_expires_at=None,
                date_updated=now,
            )
        )

        # Reject if moderator already holds a non-expired IN_REVIEW ticket
        existing = await self._session.scalar(
            select(ProductModeration).where(
                ProductModeration.status == "IN_REVIEW",
                ProductModeration.moderator_id == moderator_id,
            )
        )
        if existing is not None:
            raise ModeratorAlreadyInReviewError

        priorities = [queue_priority] if queue_priority is not None else [1, 2, 3, 4]

        for priority in priorities:
            conditions = [
                ProductModeration.status == "PENDING",
                ProductModeration.queue_priority == priority,
            ]
            if category_ids:
                conditions.append(ProductModeration.category_id.in_(category_ids))

            result = await self._session.execute(
                select(ProductModeration)
                .where(*conditions)
                .order_by(ProductModeration.date_updated.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            pm = result.scalar_one_or_none()

            if pm is None:
                continue

            pm.status = "IN_REVIEW"
            pm.moderator_id = moderator_id
            pm.claimed_at = now
            pm.claim_expires_at = now + timedelta(minutes=review_timeout_minutes)
            pm.date_updated = now

            await self._session.commit()
            return _pm_to_ticket(pm)

        await self._session.commit()
        return None
