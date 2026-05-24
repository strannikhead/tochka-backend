from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CollectionStored:
    id: UUID
    name: str
    description: str | None
    product_ids: tuple[UUID, ...]
    ordering: int


@dataclass(frozen=True)
class B2BProductImage:
    id: UUID
    url: str
    ordering: int
    is_main: bool


@dataclass(frozen=True)
class B2BProductCard:
    id: UUID
    name: str
    slug: str | None
    min_price: int
    has_stock: bool
    images: tuple[B2BProductImage, ...]


@dataclass(frozen=True)
class CollectionEnriched:
    id: UUID
    name: str
    description: str | None
    products: tuple[B2BProductCard, ...]


def enrich_collection(
    stored: CollectionStored,
    products_by_id: dict[UUID, B2BProductCard],
) -> CollectionEnriched:
    products = tuple(
        products_by_id[product_id]
        for product_id in stored.product_ids
        if product_id in products_by_id
    )
    return CollectionEnriched(
        id=stored.id,
        name=stored.name,
        description=stored.description,
        products=products,
    )
