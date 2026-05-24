from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


class OrderStatus(enum.StrEnum):
    PAID = "PAID"


@dataclass(frozen=True)
class CheckoutItemInput:
    sku_id: uuid.UUID
    quantity: int


@dataclass(frozen=True)
class CheckoutOrderInput:
    idempotency_key: uuid.UUID
    items: tuple[CheckoutItemInput, ...]
    delivery_address: str | None


@dataclass(frozen=True)
class CatalogSkuSnapshot:
    sku_id: uuid.UUID
    product_id: uuid.UUID
    product_title: str
    sku_name: str
    unit_price: int
    active_quantity: int
    product_status: str = "MODERATED"
    product_deleted: bool = False


@dataclass(frozen=True)
class ReserveFailedItem:
    sku_id: uuid.UUID
    requested: int
    available: int
    reason: str


@dataclass(frozen=True)
class ReserveRequestItem:
    sku_id: uuid.UUID
    quantity: int


@dataclass(frozen=True)
class ReserveResult:
    reserved: bool
    failed_items: tuple[ReserveFailedItem, ...] = ()


@dataclass(frozen=True)
class OrderItemSnapshot:
    id: uuid.UUID
    sku_id: uuid.UUID
    product_id: uuid.UUID
    product_title: str
    sku_name: str
    quantity: int
    unit_price: int
    line_total: int


@dataclass(frozen=True)
class OrderSnapshot:
    id: uuid.UUID
    user_id: uuid.UUID
    idempotency_key: uuid.UUID
    status: OrderStatus
    items: tuple[OrderItemSnapshot, ...]
    total_amount: int
    delivery_address: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: uuid.UUID,
        idempotency_key: uuid.UUID,
        items: tuple[OrderItemSnapshot, ...],
        delivery_address: str | None,
    ) -> OrderSnapshot:
        now = datetime.now(UTC)
        total_amount = sum(item.line_total for item in items)
        return cls(
            id=uuid.uuid4(),
            user_id=user_id,
            idempotency_key=idempotency_key,
            status=OrderStatus.PAID,
            items=items,
            total_amount=total_amount,
            delivery_address=delivery_address,
            created_at=now,
            updated_at=now,
        )
