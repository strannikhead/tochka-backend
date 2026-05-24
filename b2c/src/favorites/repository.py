from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.favorites.domain import FavoriteEntry, ProductSubscriptionEntry
from src.models import Favorite as FavoriteRow
from src.models import ProductSubscription as ProductSubscriptionRow


class FavoriteRepository(Protocol):
    async def get_user_favorites(self, user_id: UUID) -> list[FavoriteEntry]: ...
    async def add_favorite(self, user_id: UUID, product_id: UUID) -> tuple[FavoriteEntry, bool]: ...
    async def remove_favorite(self, user_id: UUID, product_id: UUID) -> None: ...
    async def get_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> ProductSubscriptionEntry | None: ...
    async def create_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
        events: list[str],
    ) -> ProductSubscriptionEntry: ...

    async def delete_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> None: ...


class InMemoryFavoriteRepository:
    def __init__(self) -> None:
        self._data: dict[tuple[UUID, UUID], FavoriteEntry] = {}
        self._subscriptions: dict[tuple[UUID, UUID], ProductSubscriptionEntry] = {}

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

    async def get_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> ProductSubscriptionEntry | None:
        return self._subscriptions.get((user_id, product_id))

    async def create_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
        events: list[str],
    ) -> ProductSubscriptionEntry:
        subscription = ProductSubscriptionEntry(
            id=uuid.uuid4(),
            user_id=user_id,
            product_id=product_id,
            events=events,
            created_at=datetime.now(UTC),
        )

        self._subscriptions[(user_id, product_id)] = subscription

        return subscription

    async def delete_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> None:
        self._subscriptions.pop((user_id, product_id), None)


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
        await self._session.commit()

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
        await self._session.commit()

    async def get_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> ProductSubscriptionEntry | None:
        result = await self._session.execute(
            select(ProductSubscriptionRow).where(
                ProductSubscriptionRow.user_id == user_id,
                ProductSubscriptionRow.product_id == product_id,
            )
        )

        row = result.scalar_one_or_none()

        if row is None:
            return None

        return ProductSubscriptionEntry(
            id=row.id,
            user_id=row.user_id,
            product_id=row.product_id,
            events=list(row.events),
            created_at=row.created_at,
        )

    async def create_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
        events: list[str],
    ) -> ProductSubscriptionEntry:
        now = datetime.now(UTC)

        subscription = ProductSubscriptionRow(
            id=uuid.uuid4(),
            user_id=user_id,
            product_id=product_id,
            events=events,
            created_at=now,
        )

        self._session.add(subscription)
        await self._session.commit()
        await self._session.refresh(subscription)

        return ProductSubscriptionEntry(
            id=subscription.id,
            user_id=subscription.user_id,
            product_id=subscription.product_id,
            events=list(subscription.events),
            created_at=subscription.created_at,
        )

    async def delete_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> None:
        await self._session.execute(
            delete(ProductSubscriptionRow).where(
                ProductSubscriptionRow.user_id == user_id,
                ProductSubscriptionRow.product_id == product_id,
            )
        )
        await self._session.commit()
