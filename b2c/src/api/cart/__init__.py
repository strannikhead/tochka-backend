from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from b2c.src.api.errors import error_response
from fastapi import APIRouter, Header

router = APIRouter(prefix="/api/v1/cart", tags=["Cart"])
legacy_router = APIRouter(tags=["cart"], include_in_schema=False)

_CARTS: dict[str, dict[str, int]] = {}


def _session_key(session_id: str | None) -> str:
    return session_id or "anonymous"


def _build_cart(session_key: str) -> dict[str, object]:
    items_map = _CARTS.get(session_key, {})
    items = [_build_cart_item(sku_id, quantity) for sku_id, quantity in items_map.items()]
    subtotal = sum(item["line_total"] for item in items)
    return {
        "id": str(uuid5(NAMESPACE_URL, session_key)),
        "items": items,
        "items_count": sum(item["quantity"] for item in items),
        "subtotal": subtotal,
        "is_valid": all(item["is_available"] for item in items),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _build_cart_item(sku_id: str, quantity: int) -> dict[str, object]:
    sku_uuid = UUID(sku_id)
    return {
        "sku_id": str(sku_uuid),
        "product_id": str(sku_uuid),
        "name": f"SKU {sku_uuid}",
        "sku_code": None,
        "quantity": quantity,
        "unit_price": 0,
        "unit_price_at_add": None,
        "line_total": 0,
        "available_quantity": 0,
        "is_available": False,
        "image": None,
    }


@router.get("")
async def get_cart(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, object]:
    return _build_cart(_session_key(x_session_id))


@router.delete("", status_code=204)
async def clear_cart(x_session_id: str | None = Header(default=None, alias="X-Session-Id")) -> None:
    _CARTS.pop(_session_key(x_session_id), None)
    return None


@router.post("/items")
async def add_cart_item(
    payload: dict[str, object],
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, object] | dict[str, object]:
    sku_id = payload.get("sku_id")
    quantity = payload.get("quantity")
    if not isinstance(sku_id, str) or not isinstance(quantity, int) or quantity < 1:
        return error_response(400, "Invalid cart item payload")

    try:
        UUID(sku_id)
    except ValueError:
        return error_response(400, "Invalid sku_id")

    session_key = _session_key(x_session_id)
    cart = _CARTS.setdefault(session_key, {})
    cart[sku_id] = cart.get(sku_id, 0) + quantity
    return _build_cart(session_key)


@router.patch("/items/{sku_id}")
async def update_cart_item(
    sku_id: str,
    payload: dict[str, object],
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, object]:
    quantity = payload.get("quantity")
    if not isinstance(quantity, int) or quantity < 1:
        return error_response(400, "Invalid cart item payload")

    try:
        UUID(sku_id)
    except ValueError:
        return error_response(400, "Invalid sku_id")

    session_key = _session_key(x_session_id)
    cart = _CARTS.setdefault(session_key, {})
    cart[sku_id] = quantity
    return _build_cart(session_key)


@router.delete("/items/{sku_id}")
async def delete_cart_item(
    sku_id: str,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, object]:
    try:
        UUID(sku_id)
    except ValueError:
        return error_response(400, "Invalid sku_id")

    session_key = _session_key(x_session_id)
    cart = _CARTS.setdefault(session_key, {})
    cart.pop(sku_id, None)
    return _build_cart(session_key)


@router.post("/validate")
async def validate_cart(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, object]:
    cart = _build_cart(_session_key(x_session_id))
    return {"is_valid": cart["is_valid"], "cart": cart, "issues": []}


@router.post("/merge")
async def merge_cart(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, object]:
    return _build_cart(_session_key(x_session_id))


@legacy_router.get("/api/v1/cart")
async def get_legacy_cart(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, object]:
    return _build_cart(_session_key(x_session_id))


@legacy_router.delete("/api/v1/cart", status_code=204)
async def clear_legacy_cart(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> None:
    _CARTS.pop(_session_key(x_session_id), None)
    return None


@legacy_router.post("/api/v1/cart/items")
async def add_legacy_cart_item(
    payload: dict[str, object],
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, object]:
    return await add_cart_item(payload, x_session_id=x_session_id)


@legacy_router.get("/api/v1/cart/items/{item_id}")
async def get_cart_item(item_id: str) -> dict[str, str]:
    return {"endpoint": "get_cart_item"}


@legacy_router.put("/api/v1/cart/items/{item_id}")
async def update_legacy_cart_item(
    item_id: str,
    payload: dict[str, object],
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, object]:
    return await update_cart_item(item_id, payload, x_session_id=x_session_id)


@legacy_router.delete("/api/v1/cart/items/{item_id}")
async def delete_legacy_cart_item(
    item_id: str,
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, object]:
    return await delete_cart_item(item_id, x_session_id=x_session_id)


@legacy_router.get("/cart/validate")
async def validate_legacy_cart(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> dict[str, object]:
    return await validate_cart(x_session_id=x_session_id)


@legacy_router.get("/api/v1/cart/also_bought")
async def get_also_bought() -> dict[str, str]:
    return {"endpoint": "get_also_bought"}
