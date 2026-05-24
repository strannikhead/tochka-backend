from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class ProductEventType(StrEnum):
    PRODUCT_BLOCKED = "PRODUCT_BLOCKED"
    PRODUCT_HARD_BLOCKED = "PRODUCT_HARD_BLOCKED"
    PRODUCT_DELETED = "PRODUCT_DELETED"
    SKU_OUT_OF_STOCK = "SKU_OUT_OF_STOCK"
    SKU_BACK_IN_STOCK = "SKU_BACK_IN_STOCK"
    PRICE_CHANGED = "PRICE_CHANGED"


class ProductEventRequest(BaseModel):
    idempotency_key: UUID
    event: ProductEventType
    product_id: UUID
    sku_ids: list[UUID] = Field(default_factory=list)
    reason: str | None = None
    date: datetime


class B2BEventProductPayload(BaseModel):
    product_id: UUID
    reason: str | None = None


class B2BEventSkuStockPayload(BaseModel):
    sku_id: UUID
    product_id: UUID
    available_quantity: int


class B2BEventPriceChangedPayload(BaseModel):
    sku_id: UUID
    product_id: UUID
    old_price: int
    new_price: int


class B2BEventRequest(BaseModel):
    event_type: ProductEventType
    idempotency_key: UUID
    occurred_at: datetime
    payload: dict[str, object]
