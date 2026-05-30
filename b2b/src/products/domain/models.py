from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class ProductImageInput:
    url: str
    ordering: int = 0


@dataclass(frozen=True)
class CharacteristicInput:
    name: str
    value: str


@dataclass(frozen=True)
class CreateProductCommand:
    """Validated input for creating a product, with seller_id sourced from the JWT."""

    seller_id: UUID
    title: str
    description: str
    category_id: UUID
    slug: str | None = None
    images: tuple[ProductImageInput, ...] = field(default_factory=tuple)
    characteristics: tuple[CharacteristicInput, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FieldReportInput:
    field_name: str
    comment: str
    sku_id: UUID | None = None


@dataclass(frozen=True)
class ModerationDecision:
    """A validated decision received from the Moderation Service."""

    idempotency_key: UUID
    product_id: UUID
    event_type: str  # MODERATED | BLOCKED
    hard_block: bool = False
    blocking_reason_id: UUID | None = None
    moderator_comment: str | None = None
    field_reports: tuple[FieldReportInput, ...] = field(default_factory=tuple)
    sender_service: str = "moderation"


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
