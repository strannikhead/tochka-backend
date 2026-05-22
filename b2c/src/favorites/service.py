from __future__ import annotations

import asyncio
from uuid import UUID

from favorites.repository import FavoriteRepository
from product_card.domain import Product, ProductStatus
from product_card.repository import ProductRepository, UpstreamServiceError


class ProductNotFoundError(Exception):
    """B2B сообщил, что товара не существует."""


class FavoritesService:
    def __init__(self, favorite_repo: FavoriteRepository, product_repo: ProductRepository) -> None:
        self._favorite_repo = favorite_repo
        self._product_repo = product_repo

    async def add(self, user_id: UUID, product_id: UUID) -> None:
        product = await self._product_repo.get_product(product_id)
        if product is None:
            raise ProductNotFoundError
        await self._favorite_repo.add_favorite(user_id, product_id)

    async def remove(self, user_id: UUID, product_id: UUID) -> None:
        await self._favorite_repo.remove_favorite(user_id, product_id)

    async def get_enriched(
        self,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Product], int]:
        entries = await self._favorite_repo.get_user_favorites(user_id)
        if not entries:
            return [], 0

        sem = asyncio.Semaphore(20)

        async def _fetch(product_id: UUID) -> Product | None:
            async with sem:
                return await self._product_repo.get_product(product_id)

        results = await asyncio.gather(
            *[_fetch(e.product_id) for e in entries],
            return_exceptions=True,
        )

        available: list[Product] = []
        for result in results:
            if isinstance(result, UpstreamServiceError):
                raise result
            if isinstance(result, BaseException) or result is None:
                continue
            if result.status != ProductStatus.MODERATED:
                continue
            available.append(result)

        total = len(available)
        return available[offset : offset + limit], total
