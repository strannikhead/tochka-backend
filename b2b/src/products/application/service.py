from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from b2b.src.products.domain.errors import CategoryNotFoundError
from b2b.src.products.domain.models import CreateProductCommand, ProductListResponse
from b2b.src.products.domain.repository import ProductsRepository

if TYPE_CHECKING:
    from b2b.src.models import Product


class ProductsService:
    def __init__(self, repository: ProductsRepository) -> None:
        self._repository = repository

    async def create_product(self, command: CreateProductCommand) -> Product:
        # Category must exist before we persist; otherwise the create is invalid.
        if not await self._repository.category_exists(command.category_id):
            raise CategoryNotFoundError("Категория не найдена")
        # A freshly created product has no SKUs, so it stays in CREATED and is NOT
        # sent to moderation — that transition is the responsibility of US-B2B-02.
        return await self._repository.create_product(command)

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
