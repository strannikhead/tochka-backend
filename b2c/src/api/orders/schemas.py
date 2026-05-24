from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel
from src.orders.domain import CheckoutItemInput, CheckoutOrderInput, OrderSnapshot


class OrderStatusFilter(StrEnum):
    CREATED = "CREATED"
    PAID = "PAID"
    ASSEMBLING = "ASSEMBLING"
    DELIVERING = "DELIVERING"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    CANCEL_PENDING = "CANCEL_PENDING"


class CheckoutOrderItemRequest(BaseModel):
    sku_id: UUID
    quantity: int

    def to_domain(self) -> CheckoutItemInput:
        return CheckoutItemInput(sku_id=self.sku_id, quantity=self.quantity)


class CheckoutOrderCreateRequest(BaseModel):
    idempotency_key: UUID
    items: list[CheckoutOrderItemRequest]
    delivery_address: str | None = None

    def to_domain(self) -> CheckoutOrderInput:
        return CheckoutOrderInput(
            idempotency_key=self.idempotency_key,
            items=tuple(item.to_domain() for item in self.items),
            delivery_address=self.delivery_address,
        )


class CheckoutOrderItemResponse(BaseModel):
    id: UUID
    sku_id: UUID
    product_id: UUID
    product_title: str
    sku_name: str
    quantity: int
    unit_price: int
    line_total: int


class CheckoutOrderResponse(BaseModel):
    id: UUID
    status: str
    items: list[CheckoutOrderItemResponse]
    total_amount: int
    delivery_address: str | None = None
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(cls, order: OrderSnapshot) -> CheckoutOrderResponse:
        return cls(
            id=order.id,
            status=order.status.value,
            items=[
                CheckoutOrderItemResponse(
                    id=item.id,
                    sku_id=item.sku_id,
                    product_id=item.product_id,
                    product_title=item.product_title,
                    sku_name=item.sku_name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                )
                for item in order.items
            ],
            total_amount=order.total_amount,
            delivery_address=order.delivery_address,
            created_at=order.created_at.isoformat().replace("+00:00", "Z"),
            updated_at=order.updated_at.isoformat().replace("+00:00", "Z"),
        )


class OrderListItemResponse(BaseModel):
    id: UUID
    status: str
    total_amount: int
    items_count: int
    created_at: str
    updated_at: str


class PaginatedOrdersResponse(BaseModel):
    items: list[OrderListItemResponse]
    total_count: int
    limit: int
    offset: int


class CancelOrderRequest(BaseModel):
    reason: str | None = None
