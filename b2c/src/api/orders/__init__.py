from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.cart.dependencies import get_cart_repository
from src.api.cart.schemas import (
    CartResponseSchema,
    CartValidationIssueSchema,
    CartValidationResponseSchema,
)
from src.api.dependencies import get_current_user_id
from src.api.orders.dependencies import (
    get_checkout_catalog_client,
    get_checkout_service,
    get_orders_repository,
)
from src.api.orders.schemas import (
    CancelOrderRequest,
    CheckoutOrderCreateRequest,
    CheckoutOrderResponse,
    OrderStatusFilter,
    PaginatedOrdersResponse,
)
from src.cart.domain import CartItemEnriched
from src.cart.repository import CartRepository
from src.database import get_session as get_main_session
from src.models import Address
from src.orders.domain import CheckoutItemInput, CheckoutOrderInput
from src.orders.repository import (
    HttpCheckoutCatalogClient,
    SqlAlchemyOrdersRepository,
    UpstreamServiceError,
)
from src.orders.service import (
    B2BUnavailableError,
    CancelNotAllowedError,
    CheckoutService,
    IdempotencyConflictError,
    InvalidQuantityError,
    InvalidRequestError,
    ReserveFailedError,
)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
OrdersRepositoryDep = Annotated[SqlAlchemyOrdersRepository, Depends(get_orders_repository)]
CartRepoDep = Annotated[CartRepository, Depends(get_cart_repository)]
MainSessionDep = Annotated[AsyncSession, Depends(get_main_session)]
CatalogClientDep = Annotated[HttpCheckoutCatalogClient, Depends(get_checkout_catalog_client)]


def _format_datetime(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _normalize_items(
    items: list[CheckoutItemInput], price_by_sku: dict[UUID, int]
) -> list[dict[str, object]]:
    return [
        {
            "sku_id": str(item.sku_id),
            "quantity": item.quantity,
            "unit_price": price_by_sku[item.sku_id],
        }
        for item in items
    ]


def _fingerprint_payload(payload: dict[str, object]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _cart_issue_for_current_state(
    *,
    sku_id: UUID,
    quantity: int,
    available_quantity: int,
    unavailable_reason: str | None,
    expected_unit_price: int | None = None,
    actual_unit_price: int | None = None,
) -> CartValidationIssueSchema:
    if unavailable_reason == "PRODUCT_BLOCKED":
        return CartValidationIssueSchema(
            sku_id=sku_id,
            type="PRODUCT_BLOCKED",
            message="Товар недоступен",
        )
    if unavailable_reason == "PRODUCT_DELETED":
        return CartValidationIssueSchema(
            sku_id=sku_id,
            type="PRODUCT_DELETED",
            message="Товар недоступен",
        )
    if unavailable_reason == "OUT_OF_STOCK" or available_quantity == 0:
        return CartValidationIssueSchema(
            sku_id=sku_id,
            type="OUT_OF_STOCK",
            message="Товар недоступен",
        )
    if (
        expected_unit_price is not None
        and actual_unit_price is not None
        and expected_unit_price != actual_unit_price
    ):
        return CartValidationIssueSchema(
            sku_id=sku_id,
            type="PRICE_CHANGED",
            message="Цена товара изменилась",
            old_value=expected_unit_price,
            new_value=actual_unit_price,
        )
    if quantity > available_quantity:
        return CartValidationIssueSchema(
            sku_id=sku_id,
            type="QUANTITY_REDUCED",
            message="Доступно меньше, чем в корзине",
            old_value=quantity,
            new_value=available_quantity,
        )
    return CartValidationIssueSchema(
        sku_id=sku_id,
        type="OUT_OF_STOCK",
        message="Товар недоступен",
    )


async def _load_address(
    session: AsyncSession,
    *,
    user_id: UUID,
    address_id: UUID,
) -> Address | None:
    address = await session.get(Address, address_id)
    if address is None or address.user_id != user_id:
        return None
    return address


async def _build_cart_validation_response(
    *,
    cart_items,
    catalog_client: HttpCheckoutCatalogClient,
    items_snapshot: list[dict[str, object]] | None,
) -> tuple[CartValidationResponseSchema, list[CheckoutItemInput], dict[UUID, int]]:
    sku_ids = [item.sku_id for item in cart_items]
    try:
        skus = await catalog_client.get_skus_by_ids(sku_ids)
    except UpstreamServiceError as exc:
        raise B2BUnavailableError() from exc
    by_id = {sku.sku_id: sku for sku in skus}

    enriched_items: list[CartItemEnriched] = []
    issues: list[CartValidationIssueSchema] = []
    snapshot_by_sku = {UUID(str(item["sku_id"])): item for item in (items_snapshot or [])}
    checkout_items: list[CheckoutItemInput] = []
    price_by_sku: dict[UUID, int] = {}

    for stored_item in cart_items:
        sku = by_id.get(stored_item.sku_id)
        quantity = stored_item.quantity
        if sku is None:
            issues.append(
                CartValidationIssueSchema(
                    sku_id=stored_item.sku_id,
                    type="PRODUCT_DELETED",
                    message="Товар недоступен",
                )
            )
            continue

        price_by_sku[stored_item.sku_id] = sku.unit_price
        checkout_items.append(CheckoutItemInput(sku_id=stored_item.sku_id, quantity=quantity))

        available_reason: str | None = None
        if sku.product_deleted:
            available_reason = "PRODUCT_DELETED"
        elif sku.product_status == "BLOCKED":
            available_reason = "PRODUCT_BLOCKED"
        elif sku.active_quantity == 0:
            available_reason = "OUT_OF_STOCK"
        elif sku.active_quantity < quantity:
            available_reason = "QUANTITY_REDUCED"

        snapshot = snapshot_by_sku.get(stored_item.sku_id)
        expected_unit_price = None
        if snapshot is not None:
            expected_unit_price = int(snapshot.get("unit_price", 0))

        if available_reason is not None:
            issues.append(
                _cart_issue_for_current_state(
                    sku_id=stored_item.sku_id,
                    quantity=quantity,
                    available_quantity=sku.active_quantity,
                    unavailable_reason=available_reason,
                    expected_unit_price=expected_unit_price,
                    actual_unit_price=sku.unit_price,
                )
            )
        elif (
            snapshot is not None
            and expected_unit_price is not None
            and expected_unit_price != sku.unit_price
        ):
            issues.append(
                _cart_issue_for_current_state(
                    sku_id=stored_item.sku_id,
                    quantity=quantity,
                    available_quantity=sku.active_quantity,
                    unavailable_reason=None,
                    expected_unit_price=expected_unit_price,
                    actual_unit_price=sku.unit_price,
                )
            )

        enriched_items.append(
            CartItemEnriched(
                item_id=stored_item.id,
                sku_id=stored_item.sku_id,
                product_id=sku.product_id,
                product_title=sku.product_title,
                sku_name=sku.sku_name,
                sku_code=None,
                image_url=None,
                unit_price=sku.unit_price,
                quantity=quantity,
                available_stock=sku.active_quantity,
                line_total=sku.unit_price * quantity,
                available=available_reason is None,
                unavailable_reason=available_reason,
            )
        )

    cart = CartResponseSchema.from_enriched(
        enriched_items,
        updated_at=max((item.updated_at for item in cart_items), default=None),
    )
    return (
        CartValidationResponseSchema(is_valid=not issues, cart=cart, issues=issues),
        checkout_items,
        price_by_sku,
    )


async def _order_response(
    *,
    order,
    user_id: UUID,
    main_session: AsyncSession,
) -> CheckoutOrderResponse | None:
    address = await _load_address(main_session, user_id=user_id, address_id=order.address_id)
    if address is None:
        return None
    return CheckoutOrderResponse.from_domain(order, address)


@router.get("")
async def list_orders(
    repository: OrdersRepositoryDep,
    user_id: CurrentUserId,
    main_session: MainSessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Annotated[OrderStatusFilter | None, Query()] = None,
) -> JSONResponse:
    orders, total_count = await repository.list_for_user(
        user_id=user_id,
        limit=limit,
        offset=offset,
        status=status.value if status is not None else None,
    )
    items: list[CheckoutOrderResponse] = []
    for order in orders:
        response = await _order_response(order=order, user_id=user_id, main_session=main_session)
        if response is not None:
            items.append(response)
    payload = PaginatedOrdersResponse(
        items=items, total_count=total_count, limit=limit, offset=offset
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.get("/{order_id}")
async def get_order(
    order_id: UUID,
    repository: OrdersRepositoryDep,
    user_id: CurrentUserId,
    main_session: MainSessionDep,
) -> JSONResponse:
    order = await repository.get_for_user(order_id=order_id, user_id=user_id)
    if order is None:
        return JSONResponse(
            status_code=404,
            content={"code": "ORDER_NOT_FOUND", "message": "Заказ не найден"},
        )

    address = await _load_address(main_session, user_id=user_id, address_id=order.address_id)
    if address is None:
        return JSONResponse(
            status_code=404,
            content={"code": "ADDRESS_NOT_FOUND", "message": "Адрес не найден"},
        )

    payload = CheckoutOrderResponse.from_domain(order, address).model_dump(mode="json")
    return JSONResponse(status_code=200, content=payload)


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: UUID,
    service: Annotated[CheckoutService, Depends(get_checkout_service)],
    user_id: CurrentUserId,
    main_session: MainSessionDep,
    payload: CancelOrderRequest | None = None,
) -> JSONResponse:
    try:
        order = await service.cancel_order(user_id=user_id, order_id=order_id)
    except CancelNotAllowedError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": str(exc),
                "current_status": exc.current_status,
            },
        )

    if order is None:
        return JSONResponse(
            status_code=404,
            content={"code": "ORDER_NOT_FOUND", "message": "Заказ не найден"},
        )

    response = await _order_response(order=order, user_id=user_id, main_session=main_session)
    if response is None:
        return JSONResponse(
            status_code=404,
            content={"code": "ADDRESS_NOT_FOUND", "message": "Адрес не найден"},
        )
    payload = response.model_dump(mode="json")
    return JSONResponse(status_code=200, content=payload)


@router.post("")
async def create_order(
    service: Annotated[CheckoutService, Depends(get_checkout_service)],
    cart_repo: CartRepoDep,
    catalog_client: CatalogClientDep,
    main_session: MainSessionDep,
    user_id: CurrentUserId,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    request: Request,
) -> JSONResponse:
    try:
        payload_data = await request.json()
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Некорректный JSON"},
        )

    try:
        payload = CheckoutOrderCreateRequest.model_validate(payload_data)
    except ValidationError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Некорректный запрос"},
        )

    address = await _load_address(main_session, user_id=user_id, address_id=payload.address_id)
    if address is None:
        return JSONResponse(
            status_code=404,
            content={"code": "ADDRESS_NOT_FOUND", "message": "Адрес не найден"},
        )

    stored_items = await cart_repo.get_items(user_id=user_id, session_id=None)
    if not stored_items:
        empty_cart = CartValidationResponseSchema(
            is_valid=False,
            cart=CartResponseSchema(items=[], items_count=0, subtotal=0, is_valid=True),
            issues=[],
        )
        return JSONResponse(status_code=422, content=empty_cart.model_dump(mode="json"))

    try:
        cart_validation, checkout_items, price_by_sku = await _build_cart_validation_response(
            cart_items=stored_items,
            catalog_client=catalog_client,
            items_snapshot=[
                item.model_dump(mode="json") for item in (payload.items_snapshot or [])
            ],
        )
    except B2BUnavailableError as exc:
        return JSONResponse(
            status_code=exc.status_code, content={"code": exc.code, "message": str(exc)}
        )

    if not cart_validation.is_valid:
        return JSONResponse(status_code=422, content=cart_validation.model_dump(mode="json"))

    request_fingerprint = _fingerprint_payload(
        {
            "address_id": str(payload.address_id),
            "payment_method_id": str(payload.payment_method_id),
            "comment": payload.comment,
            "items": _normalize_items(checkout_items, price_by_sku),
            "items_snapshot": [
                item.model_dump(mode="json") for item in (payload.items_snapshot or [])
            ],
        }
    )

    checkout_payload = CheckoutOrderInput(
        idempotency_key=idempotency_key,
        address_id=payload.address_id,
        payment_method_id=payload.payment_method_id,
        items=tuple(checkout_items),
        request_fingerprint=request_fingerprint,
    )

    try:
        order, created = await service.create_order(user_id=user_id, payload=checkout_payload)
    except InvalidRequestError as exc:
        return JSONResponse(
            status_code=exc.status_code, content={"code": exc.code, "message": str(exc)}
        )
    except InvalidQuantityError as exc:
        cart_validation = CartValidationResponseSchema(
            is_valid=False,
            cart=CartResponseSchema.from_enriched([]),
            issues=[],
        )
        return JSONResponse(
            status_code=exc.status_code, content=cart_validation.model_dump(mode="json")
        )
    except IdempotencyConflictError as exc:
        return JSONResponse(
            status_code=exc.status_code, content={"code": exc.code, "message": str(exc)}
        )
    except ReserveFailedError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": str(exc),
                "failed_items": exc.failed_items,
            },
        )
    except B2BUnavailableError as exc:
        return JSONResponse(
            status_code=exc.status_code, content={"code": exc.code, "message": str(exc)}
        )

    response = CheckoutOrderResponse.from_domain(order, address).model_dump(mode="json")
    return JSONResponse(status_code=201 if created else 200, content=response)
