from __future__ import annotations

from uuid import UUID

from b2b.src.products.domain.errors import CategoryNotFoundError
from b2b.src.products.domain.models import ProductListResponse
from b2b.src.products.domain.repository import ProductsRepository


class ProductsService:
    def __init__(self, repository: ProductsRepository) -> None:
        self._repository = repository

    async def list_products(
        self,
        *,
        category_id: UUID | None,
        filters: dict[str, list[str]],
        sort: str | None,
        limit: int,
        offset: int,
        search: str | None,
    ) -> ProductListResponse:
        if category_id is not None:
            exists = await self._repository.category_exists(category_id)
            if not exists:
                raise CategoryNotFoundError("Категория не найдена")

        return await self._repository.list_products(
            category_id=category_id,
            filters=filters,
            sort=sort,
            limit=limit,
            offset=offset,
            search=search,
        )
