from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel
from src.models import Address
from src.orders.domain import OrderSnapshot


class OrderStatusFilter(StrEnum):
    CREATED = "CREATED"
    PAID = "PAID"
    ASSEMBLING = "ASSEMBLING"
    DELIVERING = "DELIVERING"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    CANCEL_PENDING = "CANCEL_PENDING"


class CheckoutOrderSnapshotItemRequest(BaseModel):
    sku_id: UUID
    quantity: int
    unit_price: int


class CheckoutOrderCreateRequest(BaseModel):
    address_id: UUID
    payment_method_id: UUID
    comment: str | None = None
    items_snapshot: list[CheckoutOrderSnapshotItemRequest] | None = None


class CheckoutOrderItemResponse(BaseModel):
    id: UUID
    sku_id: UUID
    product_id: UUID
    name: str
    quantity: int
    unit_price: int
    line_total: int
    sku_code: str | None = None
    image_url: str | None = None

    @classmethod
    def from_domain(cls, item) -> CheckoutOrderItemResponse:
        name = " ".join(part for part in (item.product_title, item.sku_name) if part).strip()
        return cls(
            id=item.id,
            sku_id=item.sku_id,
            product_id=item.product_id,
            name=name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
            sku_code=None,
            image_url=None,
        )


class OrderAddressResponse(BaseModel):
    id: UUID
    country: str
    region: str | None = None
    city: str
    street: str
    building: str
    apartment: str | None = None
    postal_code: str | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    is_default: bool = False
    comment: str | None = None
    created_at: str

    @classmethod
    def from_model(cls, address: Address) -> OrderAddressResponse:
        return cls(
            id=address.id,
            country="Россия",
            region=None,
            city=address.city,
            street=address.street,
            building=address.house,
            apartment=address.apartment,
            postal_code=address.postal_code,
            recipient_name=None,
            recipient_phone=None,
            is_default=address.is_default,
            comment=None,
            created_at=address.created_at.isoformat().replace("+00:00", "Z"),
        )


class CheckoutOrderResponse(BaseModel):
    id: UUID
    buyer_id: UUID
    status: str
    items: list[CheckoutOrderItemResponse]
    subtotal: int
    total: int
    address: OrderAddressResponse
    comment: str | None = None
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(cls, order: OrderSnapshot, address: Address) -> CheckoutOrderResponse:
        return cls(
            id=order.id,
            buyer_id=order.user_id,
            status=order.status.value,
            items=[CheckoutOrderItemResponse.from_domain(item) for item in order.items],
            subtotal=order.total_amount,
            total=order.total_amount,
            address=OrderAddressResponse.from_model(address),
            comment=None,
            created_at=order.created_at.isoformat().replace("+00:00", "Z"),
            updated_at=order.updated_at.isoformat().replace("+00:00", "Z"),
        )


class PaginatedOrdersResponse(BaseModel):
    items: list[CheckoutOrderResponse]
    total_count: int
    limit: int
    offset: int


class CancelOrderRequest(BaseModel):
    reason: str | None = None
