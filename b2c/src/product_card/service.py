from __future__ import annotations

from uuid import UUID

from product_card.domain import Product, ProductStatus
from product_card.repository import ProductRepository


class ProductCardService:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def get_product_card(self, product_id: UUID) -> Product | None:
        product = await self._repository.get_product(product_id)
        if product is None:
            return None
        if product.status != ProductStatus.MODERATED:
            return None
        return product
