from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from favorites.domain import FavoriteEntry
from models import Favorite as FavoriteRow


class FavoriteRepository(Protocol):
    async def get_user_favorites(self, user_id: UUID) -> list[FavoriteEntry]: ...
    async def add_favorite(self, user_id: UUID, product_id: UUID) -> tuple[FavoriteEntry, bool]: ...
    async def remove_favorite(self, user_id: UUID, product_id: UUID) -> None: ...


class InMemoryFavoriteRepository:
    def __init__(self) -> None:
        self._data: dict[tuple[UUID, UUID], FavoriteEntry] = {}

    async def get_user_favorites(self, user_id: UUID) -> list[FavoriteEntry]:
        entries = [e for e in self._data.values() if e.user_id == user_id]
        return sorted(entries, key=lambda e: e.added_at, reverse=True)

    async def add_favorite(self, user_id: UUID, product_id: UUID) -> tuple[FavoriteEntry, bool]:
        key = (user_id, product_id)
        if key in self._data:
            return self._data[key], False
        entry = FavoriteEntry(user_id=user_id, product_id=product_id, added_at=datetime.now(UTC))
        self._data[key] = entry
        return entry, True

    async def remove_favorite(self, user_id: UUID, product_id: UUID) -> None:
        self._data.pop((user_id, product_id), None)


class DbFavoriteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_favorites(self, user_id: UUID) -> list[FavoriteEntry]:
        result = await self._session.execute(
            select(FavoriteRow)
            .where(FavoriteRow.user_id == user_id)
            .order_by(FavoriteRow.added_at.desc())
        )
        return [
            FavoriteEntry(user_id=row.user_id, product_id=row.product_id, added_at=row.added_at)
            for row in result.scalars().all()
        ]

    async def add_favorite(self, user_id: UUID, product_id: UUID) -> tuple[FavoriteEntry, bool]:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(FavoriteRow)
            .values(id=uuid.uuid4(), user_id=user_id, product_id=product_id, added_at=now)
            .on_conflict_do_nothing(constraint="uq_favorites_user_product")
        )
        result = await self._session.execute(stmt)
        await self._session.flush()

        # CursorResult.rowcount: 1 при вставке, 0 при конфликте on_conflict_do_nothing
        if result.rowcount > 0:  # type: ignore[attr-defined]
            return FavoriteEntry(user_id=user_id, product_id=product_id, added_at=now), True

        # Конфликт — запись уже есть, возвращаем существующую
        existing = await self._session.execute(
            select(FavoriteRow).where(
                FavoriteRow.user_id == user_id,
                FavoriteRow.product_id == product_id,
            )
        )
        row = existing.scalar_one_or_none()
        if row is None:
            # Гонка: запись удалили между нашим INSERT и SELECT — возвращаем как «не существовало»
            return FavoriteEntry(user_id=user_id, product_id=product_id, added_at=now), False
        return (
            FavoriteEntry(user_id=row.user_id, product_id=row.product_id, added_at=row.added_at),
            False,
        )

    async def remove_favorite(self, user_id: UUID, product_id: UUID) -> None:
        await self._session.execute(
            delete(FavoriteRow).where(
                FavoriteRow.user_id == user_id,
                FavoriteRow.product_id == product_id,
            )
        )
        await self._session.flush()
