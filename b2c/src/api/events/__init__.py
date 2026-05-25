from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from src.api.events.dependencies import get_product_event_service
from src.api.products.dependencies import get_product_repository
from src.events.schemas import B2BEventRequest, ProductEventRequest, ProductEventType
from src.events.service import ProductEventCommand, ProductEventService
from src.product_card.repository import ProductRepository

router = APIRouter(tags=["B2B Events"])


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"code": "UNAUTHORIZED", "message": "Требуется сервисный ключ"},
    )


def _is_service_key_valid(service_key: str | None) -> bool:
    if not service_key:
        return False
    expected_key = os.getenv("B2B_SERVICE_KEY")
    if expected_key:
        return service_key == expected_key
    return True


async def _read_json(request: Request) -> dict[str, object] | JSONResponse:
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Некорректный JSON"},
        )
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Некорректный запрос"},
        )
    return payload


@router.post("/api/v1/events/product", include_in_schema=False)
async def handle_product_event(
    request: Request,
    service: Annotated[ProductEventService, Depends(get_product_event_service)],
    service_key: Annotated[str | None, Header(alias="X-Service-Key")] = None,
) -> JSONResponse:
    if not _is_service_key_valid(service_key):
        return _unauthorized()

    payload_data = await _read_json(request)
    if isinstance(payload_data, JSONResponse):
        return payload_data

    try:
        payload = ProductEventRequest.model_validate(payload_data)
    except ValidationError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Некорректный запрос"},
        )

    await service.handle(
        ProductEventCommand(
            idempotency_key=payload.idempotency_key,
            event_type=payload.event,
            sku_ids=tuple(payload.sku_ids),
        )
    )
    return JSONResponse(status_code=200, content={"accepted": True})


@router.post("/api/v1/b2b/events")
async def handle_b2b_event(
    request: Request,
    product_repo: Annotated[ProductRepository, Depends(get_product_repository)],
    service: Annotated[ProductEventService, Depends(get_product_event_service)],
    service_key: Annotated[str | None, Header(alias="X-Service-Key")] = None,
) -> JSONResponse:
    if not _is_service_key_valid(service_key):
        return _unauthorized()

    payload_data = await _read_json(request)
    if isinstance(payload_data, JSONResponse):
        return payload_data

    try:
        payload = B2BEventRequest.model_validate(payload_data)
    except ValidationError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Некорректный запрос"},
        )

    sku_ids: list[UUID] = []
    payload_body = payload.payload
    if payload.event_type in {
        ProductEventType.PRODUCT_BLOCKED,
        ProductEventType.PRODUCT_HARD_BLOCKED,
        ProductEventType.PRODUCT_DELETED,
    }:
        product_id = UUID(str(payload_body["product_id"]))
        product = await product_repo.get_product(product_id)
        if product is not None:
            sku_ids = [sku.id for sku in product.skus]
    elif payload.event_type in {
        ProductEventType.SKU_OUT_OF_STOCK,
        ProductEventType.SKU_BACK_IN_STOCK,
    }:
        sku_ids = [UUID(str(payload_body["sku_id"]))]

    processed = await service.handle(
        ProductEventCommand(
            idempotency_key=payload.idempotency_key,
            event_type=payload.event_type,
            sku_ids=tuple(sku_ids),
        )
    )
    return JSONResponse(status_code=202 if processed else 409, content={"accepted": processed})
