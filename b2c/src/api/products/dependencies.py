from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from src.product_card.repository import HttpProductRepository, ProductRepository
from src.product_card.service import ProductCardService


def get_product_repository() -> ProductRepository:
    return HttpProductRepository()


def get_product_card_service(
    repository: Annotated[ProductRepository, Depends(get_product_repository)],
) -> ProductCardService:
    return ProductCardService(repository)
