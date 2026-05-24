from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid5

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from src.api.orders.dependencies import get_checkout_service
from src.api.orders.schemas import CheckoutOrderCreateRequest, CheckoutOrderResponse
from src.orders.service import (
    B2BUnavailableError,
    CheckoutService,
    InvalidQuantityError,
    InvalidRequestError,
    ReserveFailedError,
)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


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
