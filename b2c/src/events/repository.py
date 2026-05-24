from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import EventIdempotencyKey


class EventIdempotencyRepository(Protocol):
    async def was_processed(self, idempotency_key: UUID) -> bool: ...

    async def mark_processed(self, *, idempotency_key: UUID, event_type: str) -> None: ...


@dataclass
class InMemoryEventIdempotencyRepository:
    _keys: set[UUID] | None = None

    def __post_init__(self) -> None:
        if self._keys is None:
            self._keys = set()

    async def was_processed(self, idempotency_key: UUID) -> bool:
        return idempotency_key in self._keys

    async def mark_processed(self, *, idempotency_key: UUID, event_type: str) -> None:
        self._keys.add(idempotency_key)


class DbEventIdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def was_processed(self, idempotency_key: UUID) -> bool:
        result = await self._session.execute(
            select(EventIdempotencyKey.idempotency_key).where(
                EventIdempotencyKey.idempotency_key == idempotency_key
            )
        )
        return result.scalar_one_or_none() is not None

    async def mark_processed(self, *, idempotency_key: UUID, event_type: str) -> None:
        self._session.add(
            EventIdempotencyKey(
                idempotency_key=idempotency_key,
                event_type=event_type,
                created_at=datetime.now(UTC),
            )
        )
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
