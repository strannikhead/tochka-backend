from __future__ import annotations

from typing import Protocol
from uuid import UUID

from b2b.src.products.domain.models import ProductListResponse


class ProductsRepository(Protocol):
    async def category_exists(self, category_id: UUID) -> bool: ...

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
