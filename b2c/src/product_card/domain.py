from __future__ import annotations

import enum
from dataclasses import dataclass
from uuid import UUID


class ProductStatus(enum.StrEnum):
    CREATED = "CREATED"
    ON_MODERATION = "ON_MODERATION"
    MODERATED = "MODERATED"
    BLOCKED = "BLOCKED"
    HARD_BLOCKED = "HARD_BLOCKED"


@dataclass(frozen=True)
class Image:
    id: UUID
    url: str
    ordering: int
    alt: str | None = None
    is_main: bool | None = None


@dataclass(frozen=True)
class Characteristic:
    name: str
    value: str
    id: UUID | None = None


@dataclass(frozen=True)
class Sku:
    id: UUID
    product_id: UUID | None
    name: str
    sku_code: str | None
    price: int
    discount: int
    stock_quantity: int
    active_quantity: int
    characteristics: tuple[Characteristic, ...]
    images: tuple[Image, ...]

    @property
    def available_quantity(self) -> int:
        return self.active_quantity


@dataclass(frozen=True)
class Product:
    id: UUID
    name: str
    slug: str
    description: str
    images: tuple[Image, ...]
    status: ProductStatus
    characteristics: tuple[Characteristic, ...]
    skus: tuple[Sku, ...]
    min_price: int | None = None
