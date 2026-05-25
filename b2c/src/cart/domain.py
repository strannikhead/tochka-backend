from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CartItemStored:
    id: uuid.UUID
    user_id: uuid.UUID | None
    session_id: str | None
    sku_id: uuid.UUID
    quantity: int
    added_at: datetime
    updated_at: datetime
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class B2BSkuData:
    sku_id: uuid.UUID
    product_id: uuid.UUID
    sku_name: str
    price: int  # kopecks
    stock_quantity: int
    image_url: str | None
    product_title: str
    product_status: str  # MODERATED, BLOCKED, CREATED, ON_MODERATION
    sku_code: str | None = None


@dataclass(frozen=True)
class CartItemEnriched:
    item_id: uuid.UUID
    sku_id: uuid.UUID
    product_id: uuid.UUID
    product_title: str
    sku_name: str
    sku_code: str | None
    image_url: str | None
    unit_price: int
    quantity: int
    available_stock: int
    line_total: int
    available: bool
    unavailable_reason: str | None


_NIL_UUID = uuid.UUID(int=0)


def enrich_item(stored: CartItemStored, sku_data: B2BSkuData | None) -> CartItemEnriched:
    if sku_data is None:
        return CartItemEnriched(
            item_id=stored.id,
            sku_id=stored.sku_id,
            product_id=_NIL_UUID,
            product_title="",
            sku_name="",
            sku_code=None,
            image_url=None,
            unit_price=0,
            quantity=stored.quantity,
            available_stock=0,
            line_total=0,
            available=False,
            unavailable_reason=stored.unavailable_reason or "PRODUCT_DELETED",
        )

    unavailable_reason: str | None = None
    available = True

    if stored.unavailable_reason is not None:
        available = False
        unavailable_reason = stored.unavailable_reason
    elif sku_data.product_status == "BLOCKED":
        available = False
        unavailable_reason = "PRODUCT_BLOCKED"
    elif sku_data.product_status not in ("MODERATED",):
        available = False
        unavailable_reason = "PRODUCT_DELISTED"
    elif sku_data.stock_quantity == 0:
        available = False
        unavailable_reason = "OUT_OF_STOCK"

    line_total = sku_data.price * stored.quantity if available else 0

    return CartItemEnriched(
        item_id=stored.id,
        sku_id=stored.sku_id,
        product_id=sku_data.product_id,
        product_title=sku_data.product_title,
        sku_name=sku_data.sku_name,
        sku_code=sku_data.sku_code,
        image_url=sku_data.image_url,
        unit_price=sku_data.price,
        quantity=stored.quantity,
        available_stock=sku_data.stock_quantity,
        line_total=line_total,
        available=available,
        unavailable_reason=unavailable_reason,
    )
