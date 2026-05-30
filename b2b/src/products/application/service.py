from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from b2b.src.products.domain.errors import CategoryNotFoundError, ProductNotFoundError
from b2b.src.products.domain.models import CreateProductCommand, ProductListResponse
from b2b.src.products.domain.repository import ProductsRepository

if TYPE_CHECKING:
    from b2b.src.models import SKU, Product


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

    async def get_product_for_seller(self, product_id: UUID, seller_id: UUID) -> Product:
        # A product owned by another seller is reported as missing (404, not 403),
        # so we never disclose that it exists.
        product = await self._repository.get_product(product_id)
        if product is None or product.seller_id != seller_id:
            raise ProductNotFoundError("Товар не найден")
        return product

    async def get_product_for_service(self, product_id: UUID) -> Product:
        # Inter-service (X-Service-Key) read: no ownership scoping, public projection.
        product = await self._repository.get_product(product_id)
        if product is None:
            raise ProductNotFoundError("Товар не найден")
        return product

    async def update_product(
        self,
        product_id: UUID,
        seller_id: UUID,
        changes: dict[str, object],
    ) -> Product:
        return await self._repository.update_product(product_id, seller_id, changes)

    async def update_sku(
        self,
        sku_id: UUID,
        seller_id: UUID,
        changes: dict[str, object],
    ) -> SKU:
        return await self._repository.update_sku(sku_id, seller_id, changes)

    async def delete_product(self, product_id: UUID, seller_id: UUID) -> Product:
        # Soft delete + cascade events; ownership and already-deleted guards live in repo.
        return await self._repository.soft_delete_product(product_id, seller_id)

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
