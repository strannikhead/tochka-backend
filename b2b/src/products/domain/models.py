from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ProductListItem:
    id: UUID
    title: str
    image: str
    price: int
    in_stock: bool
    is_in_cart: bool


@dataclass(frozen=True)
class ProductListResponse:
    items: tuple[ProductListItem, ...]
    total_count: int
    limit: int
    offset: int
