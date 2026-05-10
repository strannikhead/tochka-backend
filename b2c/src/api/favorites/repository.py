from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import ProductSubscription


class FavoritesRepository(Protocol):
    async def get_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> ProductSubscription | None: ...

    async def create_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
        notify_on: list[str],
    ) -> ProductSubscription: ...

    async def delete_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> None: ...


class SqlAlchemyFavoritesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> ProductSubscription | None:
        result = await self._session.execute(
            select(ProductSubscription).where(
                ProductSubscription.user_id == user_id,
                ProductSubscription.product_id == product_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
        notify_on: list[str],
    ) -> ProductSubscription:
        subscription = ProductSubscription(
            user_id=user_id,
            product_id=product_id,
            notify_on=notify_on,
        )

        self._session.add(subscription)
        await self._session.commit()
        await self._session.refresh(subscription)

        return subscription

    async def delete_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> None:
        subscription = await self.get_product_subscription(
            user_id=user_id,
            product_id=product_id,
        )

        if subscription is None:
            return

        await self._session.delete(subscription)
        await self._session.commit()
