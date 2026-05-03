from __future__ import annotations

import enum
from dataclasses import dataclass
from uuid import UUID


class ProductStatus(enum.StrEnum):
    CREATED = "CREATED"
    ON_MODERATED = "ON_MODERATED"
    MODERATED = "MODERATED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Image:
    url: str
    order: int


@dataclass(frozen=True)
class Characteristic:
    name: str
    value: str


@dataclass(frozen=True)
class Sku:
    id: UUID
    name: str
    price: int
    discount: int
    quantity: int
    characteristics: tuple[Characteristic, ...]
    images: tuple[Image, ...]

    @property
    def in_stock(self) -> bool:
        return self.quantity > 0


@dataclass(frozen=True)
class Product:
    id: UUID
    slug: str
    title: str
    description: str
    images: tuple[Image, ...]
    status: ProductStatus
    characteristics: tuple[Characteristic, ...]
    skus: tuple[Sku, ...]
