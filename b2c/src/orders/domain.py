from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


class OrderStatus(enum.StrEnum):
    CREATED = "CREATED"
    PAID = "PAID"
    ASSEMBLING = "ASSEMBLING"
    DELIVERING = "DELIVERING"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    CANCEL_PENDING = "CANCEL_PENDING"


@dataclass(frozen=True)
class CheckoutItemInput:
    sku_id: uuid.UUID
    quantity: int


@dataclass(frozen=True)
class CheckoutOrderInput:
    idempotency_key: uuid.UUID
    address_id: uuid.UUID
    payment_method_id: uuid.UUID
    items: tuple[CheckoutItemInput, ...]
    request_fingerprint: str


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
    address_id: uuid.UUID
    payment_method_id: uuid.UUID
    request_fingerprint: str
    status: OrderStatus
    items: tuple[OrderItemSnapshot, ...]
    total_amount: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        order_id: uuid.UUID | None = None,
        user_id: uuid.UUID,
        idempotency_key: uuid.UUID,
        address_id: uuid.UUID,
        payment_method_id: uuid.UUID,
        request_fingerprint: str,
        items: tuple[OrderItemSnapshot, ...],
    ) -> OrderSnapshot:
        now = datetime.now(UTC)
        total_amount = sum(item.line_total for item in items)
        return cls(
            id=order_id or uuid.uuid4(),
            user_id=user_id,
            idempotency_key=idempotency_key,
            address_id=address_id,
            payment_method_id=payment_method_id,
            request_fingerprint=request_fingerprint,
            status=OrderStatus.PAID,
            items=items,
            total_amount=total_amount,
            created_at=now,
            updated_at=now,
        )
