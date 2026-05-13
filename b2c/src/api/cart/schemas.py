from __future__ import annotations

import uuid

from pydantic import BaseModel, field_validator
from src.cart.domain import CartItemEnriched


class CartItemSchema(BaseModel):
    item_id: uuid.UUID
    sku_id: uuid.UUID
    product_id: uuid.UUID
    product_title: str
    sku_name: str
    image_url: str | None
    unit_price: int
    quantity: int
    available_stock: int
    line_total: int
    available: bool
    unavailable_reason: str | None

    @classmethod
    def from_domain(cls, item: CartItemEnriched) -> CartItemSchema:
        return cls(
            item_id=item.item_id,
            sku_id=item.sku_id,
            product_id=item.product_id,
            product_title=item.product_title,
            sku_name=item.sku_name,
            image_url=item.image_url,
            unit_price=item.unit_price,
            quantity=item.quantity,
            available_stock=item.available_stock,
            line_total=item.line_total,
            available=item.available,
            unavailable_reason=item.unavailable_reason,
        )


class CartSummarySchema(BaseModel):
    total_amount: int
    total_items: int
    total_quantity: int
    available_items: int
    has_unavailable_items: bool
    checkout_ready: bool
    currency: str = "RUB"


class CheckoutItemSchema(BaseModel):
    product_id: uuid.UUID
    sku_id: uuid.UUID
    quantity: int
    unit_price: int
    line_total: int


class CheckoutPayloadSchema(BaseModel):
    items: list[CheckoutItemSchema]
    total_amount: int
    currency: str = "RUB"


class CartResponseSchema(BaseModel):
    items: list[CartItemSchema]
    summary: CartSummarySchema
    checkout_payload: CheckoutPayloadSchema


class CartMutationResponseSchema(BaseModel):
    message: str
    item: CartItemSchema
    summary: CartSummarySchema


class AddCartItemRequest(BaseModel):
    sku_id: uuid.UUID
    quantity: int = 1

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be >= 1")
        return v


class UpdateCartItemRequest(BaseModel):
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be >= 1")
        return v


class MergeCartRequest(BaseModel):
    session_id: str


def build_summary(items: list[CartItemEnriched]) -> CartSummarySchema:
    available = [item for item in items if item.available]
    return CartSummarySchema(
        total_amount=sum(item.line_total for item in available),
        total_items=len(items),
        total_quantity=sum(item.quantity for item in items),
        available_items=len(available),
        has_unavailable_items=len(items) > len(available),
        checkout_ready=bool(available) and len(available) == len(items),
    )


def build_checkout_payload(items: list[CartItemEnriched]) -> CheckoutPayloadSchema:
    available = [item for item in items if item.available]
    checkout_items = [
        CheckoutItemSchema(
            product_id=item.product_id,
            sku_id=item.sku_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
        )
        for item in available
    ]
    return CheckoutPayloadSchema(
        items=checkout_items,
        total_amount=sum(item.line_total for item in available),
    )
