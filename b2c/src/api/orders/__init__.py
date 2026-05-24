from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid5

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from src.api.dependencies import get_current_user_id
from src.api.orders.dependencies import get_checkout_service, get_orders_repository
from src.api.orders.schemas import (
    CancelOrderRequest,
    CheckoutOrderCreateRequest,
    CheckoutOrderResponse,
    OrderListItemResponse,
    OrderStatusFilter,
    PaginatedOrdersResponse,
)
from src.orders.repository import SqlAlchemyOrdersRepository
from src.orders.service import (
    B2BUnavailableError,
    CancelNotAllowedError,
    CheckoutService,
    InvalidQuantityError,
    InvalidRequestError,
    ReserveFailedError,
)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
OrdersRepositoryDep = Annotated[SqlAlchemyOrdersRepository, Depends(get_orders_repository)]


def _format_datetime(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@router.get("")
async def list_orders(
    repository: OrdersRepositoryDep,
    user_id: CurrentUserId,
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
    payload = PaginatedOrdersResponse(
        items=[
            OrderListItemResponse(
                id=order.id,
                status=order.status.value,
                total_amount=order.total_amount,
                items_count=sum(item.quantity for item in order.items),
                created_at=_format_datetime(order.created_at),
                updated_at=_format_datetime(order.updated_at),
            )
            for order in orders
        ],
        total_count=total_count,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))


@router.get("/{order_id}")
async def get_order(
    order_id: UUID,
    repository: OrdersRepositoryDep,
    user_id: CurrentUserId,
) -> JSONResponse:
    order = await repository.get_for_user(order_id=order_id, user_id=user_id)
    if order is None:
        return JSONResponse(
            status_code=404,
            content={"code": "ORDER_NOT_FOUND", "message": "Заказ не найден"},
        )

    payload = CheckoutOrderResponse.from_domain(order).model_dump(mode="json")
    return JSONResponse(status_code=200, content=payload)


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: UUID,
    service: Annotated[CheckoutService, Depends(get_checkout_service)],
    user_id: CurrentUserId,
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

    payload = CheckoutOrderResponse.from_domain(order).model_dump(mode="json")
    return JSONResponse(status_code=200, content=payload)


@router.post("")
async def create_order(
    request: Request,
    service: Annotated[CheckoutService, Depends(get_checkout_service)],
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    user_id = _parse_user_id(authorization)
    if user_id is None:
        return JSONResponse(
            status_code=401, content={"code": "UNAUTHORIZED", "message": "Требуется авторизация"}
        )

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

    try:
        order, created = await service.create_order(user_id=user_id, payload=payload.to_domain())
    except InvalidRequestError as exc:
        return JSONResponse(
            status_code=exc.status_code, content={"code": exc.code, "message": str(exc)}
        )
    except InvalidQuantityError as exc:
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

    response = CheckoutOrderResponse.from_domain(order).model_dump(mode="json")
    return JSONResponse(status_code=201 if created else 200, content=response)


def _parse_user_id(authorization: str | None) -> UUID | None:
    if authorization is None:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    token = authorization[len(prefix) :].strip()
    if not token:
        return None
    try:
        return UUID(token)
    except ValueError:
        return uuid5(UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), token)
