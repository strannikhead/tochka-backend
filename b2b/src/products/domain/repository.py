from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from b2b.src.products.domain.models import CreateProductCommand, ProductListResponse

if TYPE_CHECKING:
    from b2b.src.models import SKU, Product


class ProductsRepository(Protocol):
    async def category_exists(self, category_id: UUID) -> bool: ...

    async def create_product(self, command: CreateProductCommand) -> Product: ...

    async def get_product(self, product_id: UUID) -> Product | None: ...

    async def update_product(
        self,
        product_id: UUID,
        seller_id: UUID,
        changes: dict[str, object],
    ) -> Product: ...

    async def update_sku(
        self,
        sku_id: UUID,
        seller_id: UUID,
        changes: dict[str, object],
    ) -> SKU: ...

    async def list_products(
        self,
        *,
        category_id: UUID | None,
        filters: dict[str, list[str]],
        sort: str | None,
        limit: int,
        offset: int,
        search: str | None,
    ) -> ProductListResponse: ...
