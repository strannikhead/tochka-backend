from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.cart.domain import CartItemEnriched


class ImageRefSchema(BaseModel):
    id: uuid.UUID
    url: str
    alt: str | None = None
    ordering: int = 0
    is_main: bool | None = None


class CartItemSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sku_id: uuid.UUID
    product_id: uuid.UUID
    name: str
    sku_code: str | None = None
    quantity: int
    unit_price: int
    unit_price_at_add: int | None = None
    line_total: int
    available_quantity: int = Field(ge=0)
    is_available: bool
    image: ImageRefSchema | None = None

    @classmethod
    def from_domain(cls, item: CartItemEnriched) -> CartItemSchema:
        name = " ".join(part for part in (item.product_title, item.sku_name) if part)
        return cls(
            sku_id=item.sku_id,
            product_id=item.product_id,
            name=name,
            sku_code=item.sku_code,
            quantity=item.quantity,
            unit_price=item.unit_price,
            unit_price_at_add=None,
            line_total=item.line_total,
            available_quantity=item.available_stock,
            is_available=item.available,
            image=None,
        )


class CartResponseSchema(BaseModel):
    id: uuid.UUID | None = None
    items: list[CartItemSchema]
    items_count: int
    subtotal: int
    is_valid: bool
    updated_at: datetime | None = None

    @classmethod
    def from_enriched(
        cls,
        items: list[CartItemEnriched],
        *,
        cart_id: uuid.UUID | None = None,
        updated_at: datetime | None = None,
    ) -> CartResponseSchema:
        subtotal = sum(item.line_total for item in items)
        items_count = sum(item.quantity for item in items)
        is_valid = bool(items) and all(
            item.available and item.quantity <= item.available_stock for item in items
        )
        if not items:
            is_valid = True
        return cls(
            id=cart_id,
            items=[CartItemSchema.from_domain(item) for item in items],
            items_count=items_count,
            subtotal=subtotal,
            is_valid=is_valid,
            updated_at=updated_at,
        )


# enum from OpenAPI: PRICE_CHANGED, OUT_OF_STOCK, QUANTITY_REDUCED, PRODUCT_BLOCKED, PRODUCT_DELETED
CartIssueType = str


class CartValidationIssueSchema(BaseModel):
    sku_id: uuid.UUID
    type: CartIssueType
    message: str
    old_value: int | str | None = None
    new_value: int | str | None = None


class CartValidationResponseSchema(BaseModel):
    is_valid: bool
    cart: CartResponseSchema
    issues: list[CartValidationIssueSchema]


class CartItemAddRequest(BaseModel):
    sku_id: uuid.UUID
    quantity: int = 1

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be >= 1")
        return v


class CartItemQuantityRequest(BaseModel):
    quantity: int

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("quantity must be >= 1")
        return v
