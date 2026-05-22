from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ProductShort:
    id: UUID
    title: str
    image: str
    price: int
    in_stock: bool
    is_in_cart: bool


@dataclass(frozen=True)
class ProductShortList:
    items: tuple[ProductShort, ...]
    total_count: int
    limit: int
    offset: int


@dataclass(frozen=True)
class FacetValue:
    value: str
    count: int


@dataclass(frozen=True)
class Facet:
    name: str
    values: tuple[FacetValue, ...]


@dataclass(frozen=True)
class Facets:
    category_id: UUID
    facets: tuple[Facet, ...]
