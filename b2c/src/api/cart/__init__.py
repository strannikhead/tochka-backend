from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse
from src.api.cart.dependencies import get_b2b_cart_client, get_cart_repository
from src.api.cart.schemas import (
    CartItemAddRequest,
    CartItemQuantityRequest,
    CartResponseSchema,
    CartValidationIssueSchema,
    CartValidationResponseSchema,
)
from src.api.dependencies import get_optional_user_id
from src.cart.b2b_client import B2BCartClient, B2BCartError
from src.cart.domain import CartItemEnriched, CartItemStored, enrich_item
from src.cart.repository import CartRepository

router = APIRouter(tags=["cart"])

CartRepo = Annotated[CartRepository, Depends(get_cart_repository)]
B2BClient = Annotated[B2BCartClient, Depends(get_b2b_cart_client)]
OptionalUserId = Annotated[uuid.UUID | None, Depends(get_optional_user_id)]


def _missing_identity() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "code": "MISSING_CART_IDENTITY",
            "message": "Требуется Authorization или X-Session-Id",
        },
    )


def _service_unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "code": "SERVICE_UNAVAILABLE",
            "message": "Сервис временно недоступен, попробуйте позже",
        },
    )


def _parse_session_id(raw: str | None) -> uuid.UUID | None | JSONResponse:
    if raw is None or raw == "":
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_SESSION_ID", "message": "X-Session-Id должен быть UUID"},
        )


def _resolve_identity(
    user_id: uuid.UUID | None, x_session_id: str | None
) -> tuple[uuid.UUID | None, str | None] | JSONResponse:
    """JWT user_id wins; otherwise require X-Session-Id (uuid)."""
    if user_id is not None:
        return user_id, None
    parsed = _parse_session_id(x_session_id)
    if isinstance(parsed, JSONResponse):
        return parsed
    if parsed is None:
        return _missing_identity()
    return None, str(parsed)


async def _enrich_all(
    stored_items: list[CartItemStored], b2b: B2BCartClient
) -> list[CartItemEnriched] | None:
    enriched: list[CartItemEnriched] = []
    for stored in stored_items:
        try:
            sku_data = await b2b.get_sku_data(stored.sku_id)
        except B2BCartError:
            return None
        enriched.append(enrich_item(stored, sku_data))
    return enriched


def _stored_updated_at(items: list[CartItemStored]) -> object:
    if not items:
        return None
    return max(item.updated_at for item in items)


@router.get("/api/v1/cart", response_model=None)
async def get_cart(
    repo: CartRepo,
    b2b: B2BClient,
    user_id: OptionalUserId,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> CartResponseSchema | JSONResponse:
    identity = _resolve_identity(user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    uid, sid = identity

    stored = await repo.get_items(user_id=uid, session_id=sid)
    enriched = await _enrich_all(stored, b2b)
    if enriched is None:
        return _service_unavailable()

    return CartResponseSchema.from_enriched(
        enriched,
        updated_at=_stored_updated_at(stored),  # type: ignore[arg-type]
    )


@router.delete("/api/v1/cart", status_code=204, response_model=None)
async def clear_cart(
    repo: CartRepo,
    user_id: OptionalUserId,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> Response | JSONResponse:
    identity = _resolve_identity(user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    uid, sid = identity
    await repo.clear(user_id=uid, session_id=sid)
    return Response(status_code=204)


@router.post("/api/v1/cart/items", response_model=None)
async def add_cart_item(
    body: CartItemAddRequest,
    repo: CartRepo,
    b2b: B2BClient,
    user_id: OptionalUserId,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> CartResponseSchema | JSONResponse:
    identity = _resolve_identity(user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    uid, sid = identity

    try:
        sku_data, error_code = await b2b.check_sku_for_add(body.sku_id, body.quantity)
    except B2BCartError:
        return _service_unavailable()

    if error_code == "SKU_NOT_FOUND":
        return JSONResponse(
            status_code=404,
            content={"code": "SKU_NOT_FOUND", "message": "SKU не найден"},
        )
    if error_code == "SKU_NOT_AVAILABLE":
        return JSONResponse(
            status_code=404,
            content={"code": "SKU_NOT_AVAILABLE", "message": "Товар недоступен"},
        )
    if error_code == "INSUFFICIENT_STOCK":
        available = sku_data.stock_quantity if sku_data else 0
        return JSONResponse(
            status_code=409,
            content={
                "code": "INSUFFICIENT_STOCK",
                "message": f"Недостаточно остатков, доступно {available}",
            },
        )

    await repo.upsert_item(user_id=uid, session_id=sid, sku_id=body.sku_id, quantity=body.quantity)

    stored = await repo.get_items(user_id=uid, session_id=sid)
    enriched = await _enrich_all(stored, b2b)
    if enriched is None:
        return _service_unavailable()
    return CartResponseSchema.from_enriched(
        enriched,
        updated_at=_stored_updated_at(stored),  # type: ignore[arg-type]
    )


@router.patch("/api/v1/cart/items/{sku_id}", response_model=None)
async def update_cart_item(
    sku_id: uuid.UUID,
    body: CartItemQuantityRequest,
    repo: CartRepo,
    b2b: B2BClient,
    user_id: OptionalUserId,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> CartResponseSchema | JSONResponse:
    identity = _resolve_identity(user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    uid, sid = identity

    existing = await repo.get_items(user_id=uid, session_id=sid)
    if not any(item.sku_id == sku_id for item in existing):
        return JSONResponse(
            status_code=404,
            content={"code": "CART_ITEM_NOT_FOUND", "message": "Позиция не найдена"},
        )

    try:
        sku_data, error_code = await b2b.check_sku_for_add(sku_id, body.quantity)
    except B2BCartError:
        return _service_unavailable()

    if error_code == "INSUFFICIENT_STOCK":
        available = sku_data.stock_quantity if sku_data else 0
        return JSONResponse(
            status_code=409,
            content={
                "code": "INSUFFICIENT_STOCK",
                "message": f"Недостаточно остатков, доступно {available}",
            },
        )

    await repo.set_item_quantity_by_sku(
        sku_id=sku_id, user_id=uid, session_id=sid, quantity=body.quantity
    )

    stored = await repo.get_items(user_id=uid, session_id=sid)
    enriched = await _enrich_all(stored, b2b)
    if enriched is None:
        return _service_unavailable()
    return CartResponseSchema.from_enriched(
        enriched,
        updated_at=_stored_updated_at(stored),  # type: ignore[arg-type]
    )


@router.delete("/api/v1/cart/items/{sku_id}", response_model=None)
async def delete_cart_item(
    sku_id: uuid.UUID,
    repo: CartRepo,
    b2b: B2BClient,
    user_id: OptionalUserId,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> CartResponseSchema | JSONResponse:
    identity = _resolve_identity(user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    uid, sid = identity

    deleted = await repo.delete_item_by_sku(sku_id=sku_id, user_id=uid, session_id=sid)
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={"code": "CART_ITEM_NOT_FOUND", "message": "Позиция не найдена"},
        )

    stored = await repo.get_items(user_id=uid, session_id=sid)
    enriched = await _enrich_all(stored, b2b)
    if enriched is None:
        return _service_unavailable()
    return CartResponseSchema.from_enriched(
        enriched,
        updated_at=_stored_updated_at(stored),  # type: ignore[arg-type]
    )


def _issue_for(item: CartItemEnriched) -> CartValidationIssueSchema | None:
    if item.available and item.quantity <= item.available_stock:
        return None
    reason = item.unavailable_reason or "QUANTITY_REDUCED"
    if not item.available:
        issue_type = reason
        message = "Товар недоступен"
        old_value: int | None = None
        new_value: int | None = None
    else:
        issue_type = "QUANTITY_REDUCED"
        message = "Доступно меньше, чем в корзине"
        old_value = item.quantity
        new_value = item.available_stock
    return CartValidationIssueSchema(
        sku_id=item.sku_id,
        type=issue_type,
        message=message,
        old_value=old_value,
        new_value=new_value,
    )


@router.post("/api/v1/cart/validate", response_model=None)
async def validate_cart(
    repo: CartRepo,
    b2b: B2BClient,
    user_id: OptionalUserId,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> CartValidationResponseSchema | JSONResponse:
    identity = _resolve_identity(user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    uid, sid = identity

    stored = await repo.get_items(user_id=uid, session_id=sid)
    enriched = await _enrich_all(stored, b2b)
    if enriched is None:
        return _service_unavailable()

    issues = [issue for issue in (_issue_for(item) for item in enriched) if issue is not None]
    cart = CartResponseSchema.from_enriched(
        enriched,
        updated_at=_stored_updated_at(stored),  # type: ignore[arg-type]
    )
    return CartValidationResponseSchema(
        is_valid=not issues,
        cart=cart,
        issues=issues,
    )


@router.post("/api/v1/cart/merge", response_model=None)
async def merge_cart(
    repo: CartRepo,
    b2b: B2BClient,
    user_id: OptionalUserId,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> CartResponseSchema | JSONResponse:
    if user_id is None:
        return JSONResponse(
            status_code=401,
            content={"code": "UNAUTHORIZED", "message": "Требуется авторизация"},
        )
    parsed = _parse_session_id(x_session_id)
    if isinstance(parsed, JSONResponse):
        return parsed
    if parsed is None:
        return JSONResponse(
            status_code=400,
            content={
                "code": "MISSING_SESSION_ID",
                "message": "X-Session-Id обязателен для merge",
            },
        )
    await repo.merge_guest_into_user(session_id=str(parsed), user_id=user_id)

    stored = await repo.get_items(user_id=user_id, session_id=None)
    enriched = await _enrich_all(stored, b2b)
    if enriched is None:
        return _service_unavailable()
    return CartResponseSchema.from_enriched(
        enriched,
        updated_at=_stored_updated_at(stored),  # type: ignore[arg-type]
    )
