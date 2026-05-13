from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from src.api.cart.dependencies import get_b2b_cart_client, get_cart_repository
from src.api.cart.schemas import (
    AddCartItemRequest,
    CartItemSchema,
    CartMutationResponseSchema,
    CartResponseSchema,
    MergeCartRequest,
    UpdateCartItemRequest,
    build_checkout_payload,
    build_summary,
)
from src.cart.b2b_client import B2BCartClient, B2BCartError
from src.cart.domain import enrich_item
from src.cart.repository import CartRepository

router = APIRouter(tags=["cart"])

CartRepo = Annotated[CartRepository, Depends(get_cart_repository)]
B2BClient = Annotated[B2BCartClient, Depends(get_b2b_cart_client)]

_MISSING_IDENTITY = JSONResponse(
    status_code=400,
    content={"code": "MISSING_CART_IDENTITY", "message": "Передайте X-User-Id или X-Session-Id"},
)
_SERVICE_UNAVAILABLE = JSONResponse(
    status_code=503,
    content={
        "code": "SERVICE_UNAVAILABLE",
        "message": "Сервис временно недоступен, попробуйте позже",
    },
)


def _extract_identity(
    x_user_id: str | None,
    x_session_id: str | None,
) -> tuple[uuid.UUID | None, str | None] | JSONResponse:
    user_id: uuid.UUID | None = None
    if x_user_id:
        try:
            user_id = uuid.UUID(x_user_id)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"code": "INVALID_USER_ID", "message": "Invalid X-User-Id format"},
            )
    if user_id is not None:
        return user_id, None
    session_id = x_session_id or None
    if session_id is None:
        return _MISSING_IDENTITY
    return None, session_id


async def _enrich_all(stored_items, b2b: B2BCartClient):
    enriched = []
    for stored in stored_items:
        try:
            sku_data = await b2b.get_sku_data(stored.sku_id)
        except B2BCartError:
            return None
        enriched.append(enrich_item(stored, sku_data))
    return enriched


@router.get("/api/v1/cart", response_model=None)
async def get_cart(
    repo: CartRepo,
    b2b: B2BClient,
    x_user_id: Annotated[str | None, Header()] = None,
    x_session_id: Annotated[str | None, Header()] = None,
) -> CartResponseSchema | JSONResponse:
    identity = _extract_identity(x_user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    user_id, session_id = identity

    stored = await repo.get_items(user_id=user_id, session_id=session_id)
    enriched = await _enrich_all(stored, b2b)
    if enriched is None:
        return _SERVICE_UNAVAILABLE

    return CartResponseSchema(
        items=[CartItemSchema.from_domain(item) for item in enriched],
        summary=build_summary(enriched),
        checkout_payload=build_checkout_payload(enriched),
    )


@router.delete("/api/v1/cart", status_code=204, response_model=None)
async def clear_cart(
    repo: CartRepo,
    x_user_id: Annotated[str | None, Header()] = None,
    x_session_id: Annotated[str | None, Header()] = None,
) -> None | JSONResponse:
    identity = _extract_identity(x_user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    user_id, session_id = identity
    await repo.clear(user_id=user_id, session_id=session_id)


@router.post("/api/v1/cart/items", response_model=None)
async def add_cart_item(
    body: AddCartItemRequest,
    repo: CartRepo,
    b2b: B2BClient,
    x_user_id: Annotated[str | None, Header()] = None,
    x_session_id: Annotated[str | None, Header()] = None,
) -> CartMutationResponseSchema | JSONResponse:
    identity = _extract_identity(x_user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    user_id, session_id = identity

    try:
        sku_data, error_code = await b2b.check_sku_for_add(body.sku_id, body.quantity)
    except B2BCartError:
        return _SERVICE_UNAVAILABLE

    if error_code == "SKU_NOT_FOUND":
        return JSONResponse(
            status_code=404,
            content={"code": "SKU_NOT_FOUND", "message": "SKU с указанным id не существует"},
        )
    if error_code == "SKU_NOT_AVAILABLE":
        return JSONResponse(
            status_code=410,
            content={"code": "SKU_NOT_AVAILABLE", "message": "Товар недоступен для покупки"},
        )
    if error_code == "INSUFFICIENT_STOCK":
        available = sku_data.stock_quantity if sku_data else 0
        return JSONResponse(
            status_code=422,
            content={
                "code": "INSUFFICIENT_STOCK",
                "message": f"Нельзя добавить {body.quantity}, доступно только {available}",
            },
        )

    stored, is_new = await repo.upsert_item(
        user_id=user_id,
        session_id=session_id,
        sku_id=body.sku_id,
        quantity=body.quantity,
    )
    enriched_item = enrich_item(stored, sku_data)

    all_stored = await repo.get_items(user_id=user_id, session_id=session_id)
    all_enriched = await _enrich_all(all_stored, b2b)
    if all_enriched is None:
        all_enriched = [enriched_item]

    message = "Позиция добавлена в корзину" if is_new else "Количество в корзине увеличено"
    response = CartMutationResponseSchema(
        message=message,
        item=CartItemSchema.from_domain(enriched_item),
        summary=build_summary(all_enriched),
    )
    status_code = 201 if is_new else 200
    return JSONResponse(status_code=status_code, content=response.model_dump(mode="json"))


@router.get("/api/v1/cart/items/{item_id}", response_model=None)
async def get_cart_item(
    item_id: uuid.UUID,
    repo: CartRepo,
    b2b: B2BClient,
    x_user_id: Annotated[str | None, Header()] = None,
    x_session_id: Annotated[str | None, Header()] = None,
) -> CartItemSchema | JSONResponse:
    identity = _extract_identity(x_user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    user_id, session_id = identity

    stored = await repo.get_item(item_id=item_id, user_id=user_id, session_id=session_id)
    if stored is None:
        return JSONResponse(
            status_code=404,
            content={"code": "CART_ITEM_NOT_FOUND", "message": "Позиция не найдена в корзине"},
        )
    try:
        sku_data = await b2b.get_sku_data(stored.sku_id)
    except B2BCartError:
        return _SERVICE_UNAVAILABLE
    return CartItemSchema.from_domain(enrich_item(stored, sku_data))


@router.put("/api/v1/cart/items/{item_id}", response_model=None)
async def update_cart_item(
    item_id: uuid.UUID,
    body: UpdateCartItemRequest,
    repo: CartRepo,
    b2b: B2BClient,
    x_user_id: Annotated[str | None, Header()] = None,
    x_session_id: Annotated[str | None, Header()] = None,
) -> CartMutationResponseSchema | JSONResponse:
    identity = _extract_identity(x_user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    user_id, session_id = identity

    stored = await repo.get_item(item_id=item_id, user_id=user_id, session_id=session_id)
    if stored is None:
        return JSONResponse(
            status_code=404,
            content={"code": "CART_ITEM_NOT_FOUND", "message": "Позиция не найдена в корзине"},
        )

    try:
        sku_data, error_code = await b2b.check_sku_for_add(stored.sku_id, body.quantity)
    except B2BCartError:
        return _SERVICE_UNAVAILABLE

    if error_code == "SKU_NOT_AVAILABLE":
        return JSONResponse(
            status_code=410,
            content={
                "code": "PRODUCT_NOT_AVAILABLE",
                "message": "Товар недоступен и не может быть обновлён",
            },
        )
    if error_code == "INSUFFICIENT_STOCK":
        available = sku_data.stock_quantity if sku_data else 0
        return JSONResponse(
            status_code=422,
            content={
                "code": "INSUFFICIENT_STOCK",
                "message": f"Нельзя установить {body.quantity}, доступно только {available}",
            },
        )

    updated = await repo.set_item_quantity(
        item_id=item_id,
        user_id=user_id,
        session_id=session_id,
        quantity=body.quantity,
    )
    if updated is None:
        return JSONResponse(
            status_code=404,
            content={"code": "CART_ITEM_NOT_FOUND", "message": "Позиция не найдена в корзине"},
        )

    enriched_item = enrich_item(updated, sku_data)
    all_stored = await repo.get_items(user_id=user_id, session_id=session_id)
    all_enriched = await _enrich_all(all_stored, b2b)
    if all_enriched is None:
        all_enriched = [enriched_item]

    return CartMutationResponseSchema(
        message="Количество обновлено",
        item=CartItemSchema.from_domain(enriched_item),
        summary=build_summary(all_enriched),
    )


@router.delete("/api/v1/cart/items/{item_id}", status_code=204, response_model=None)
async def delete_cart_item(
    item_id: uuid.UUID,
    repo: CartRepo,
    x_user_id: Annotated[str | None, Header()] = None,
    x_session_id: Annotated[str | None, Header()] = None,
) -> None | JSONResponse:
    identity = _extract_identity(x_user_id, x_session_id)
    if isinstance(identity, JSONResponse):
        return identity
    user_id, session_id = identity
    deleted = await repo.delete_item(item_id=item_id, user_id=user_id, session_id=session_id)
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={"code": "CART_ITEM_NOT_FOUND", "message": "Позиция не найдена в корзине"},
        )


@router.post("/api/v1/cart/merge", response_model=None)
async def merge_cart(
    body: MergeCartRequest,
    repo: CartRepo,
    x_user_id: Annotated[str | None, Header()] = None,
) -> dict[str, str] | JSONResponse:
    """Слить гостевую корзину в корзину авторизованного пользователя. Вызывается после логина."""
    if not x_user_id:
        return JSONResponse(
            status_code=400,
            content={"code": "MISSING_CART_IDENTITY", "message": "X-User-Id обязателен для merge"},
        )
    try:
        user_id = uuid.UUID(x_user_id)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_USER_ID", "message": "Invalid X-User-Id"},
        )
    await repo.merge_guest_into_user(session_id=body.session_id, user_id=user_id)
    return {"message": "Корзины объединены"}


@router.get("/api/v1/cart/validate")
async def validate_cart() -> dict[str, str]:
    return {"endpoint": "validate_cart"}


@router.get("/cart/validate")
async def validate_cart_legacy() -> dict[str, str]:
    return {"endpoint": "validate_cart"}


@router.get("/api/v1/cart/also_bought")
async def get_also_bought() -> dict[str, str]:
    return {"endpoint": "get_also_bought"}
