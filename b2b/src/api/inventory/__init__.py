from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from b2b.src.b2c_client import B2cClient
from b2b.src.config import get_settings
from b2b.src.db import get_session
from b2b.src.inventory.models import (
    FulfilledOrder,
    InventoryReservation,
    InventoryReservationItem,
    InventoryReservationStatus,
)
from b2b.src.models import SKU, Product, ProductStatus

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


class InventoryItemRequest(BaseModel):
    sku_id: UUID
    quantity: int = Field(ge=1)


class ReserveRequest(BaseModel):
    idempotency_key: UUID
    order_id: UUID
    items: list[InventoryItemRequest]


class UnreserveRequest(BaseModel):
    order_id: UUID
    items: list[InventoryItemRequest]


def _get_b2c_client() -> B2cClient:
    settings = get_settings()
    return B2cClient(base_url=settings.b2c.url, service_key=settings.b2c.service_key)


@router.post("/reserve")
async def reserve_inventory(
    payload: dict,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
) -> JSONResponse:
    try:
        request = ReserveRequest.model_validate(payload)
    except ValidationError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Invalid reserve payload"},
        )

    if x_service_key is None:
        return JSONResponse(
            status_code=401, content={"code": "UNAUTHORIZED", "message": "Missing service key"}
        )

    existing_stmt = (
        select(InventoryReservation)
        .where(InventoryReservation.idempotency_key == request.idempotency_key)
        .limit(1)
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        return JSONResponse(
            status_code=200,
            content={
                "order_id": str(existing.order_id),
                "status": "RESERVED",
                "reserved_at": existing.reserved_at.isoformat().replace("+00:00", "Z"),
            },
        )

    # Lock rows in consistent order (by id) to prevent deadlocks under concurrency.
    sorted_sku_ids = sorted(request.items, key=lambda i: i.sku_id)
    sku_ids = [item.sku_id for item in sorted_sku_ids]
    stmt = select(SKU).where(SKU.id.in_(sku_ids)).order_by(SKU.id).with_for_update()
    rows = (await session.execute(stmt)).scalars().all()
    by_id = {row.id: row for row in rows}

    failed_items: list[dict[str, object]] = []
    for item in request.items:
        sku = by_id.get(item.sku_id)
        if sku is None:
            failed_items.append(
                {
                    "sku_id": str(item.sku_id),
                    "requested": item.quantity,
                    "available": 0,
                    "reason": "SKU_NOT_FOUND",
                }
            )
            continue
        product = await session.get(Product, sku.product_id)
        if product is None or product.deleted:
            failed_items.append(
                {
                    "sku_id": str(item.sku_id),
                    "requested": item.quantity,
                    "available": int(sku.active_quantity),
                    "reason": "PRODUCT_DELETED",
                }
            )
            continue
        if product.status in {ProductStatus.BLOCKED, ProductStatus.HARD_BLOCKED}:
            failed_items.append(
                {
                    "sku_id": str(item.sku_id),
                    "requested": item.quantity,
                    "available": int(sku.active_quantity),
                    "reason": "PRODUCT_BLOCKED",
                }
            )
            continue
        if sku.active_quantity < item.quantity:
            failed_items.append(
                {
                    "sku_id": str(item.sku_id),
                    "requested": item.quantity,
                    "available": int(sku.active_quantity),
                    "reason": "INSUFFICIENT_STOCK" if sku.active_quantity > 0 else "OUT_OF_STOCK",
                }
            )

    if failed_items:
        return JSONResponse(
            status_code=409,
            content={
                "code": "RESERVE_FAILED",
                "message": "Не удалось зарезервировать товары",
                "details": {"failed_items": failed_items},
            },
        )

    # All-or-nothing: update both quantities atomically.
    out_of_stock_skus: list[SKU] = []
    for item in request.items:
        sku = by_id[item.sku_id]
        sku.active_quantity -= item.quantity
        sku.reserved_quantity += item.quantity
        if sku.active_quantity == 0:
            out_of_stock_skus.append(sku)

    reservation = InventoryReservation(
        order_id=request.order_id,
        idempotency_key=request.idempotency_key,
        status=InventoryReservationStatus.RESERVED,
        failed_items=[],
    )
    reservation.items = [
        InventoryReservationItem(
            sku_id=item.sku_id,
            requested=item.quantity,
            remaining_stock=by_id[item.sku_id].active_quantity,
            reason=None,
        )
        for item in request.items
    ]
    session.add(reservation)
    await session.commit()

    # Fire-and-forget: notify B2C for each SKU that just ran out of stock.
    if out_of_stock_skus:
        b2c = _get_b2c_client()
        for sku in out_of_stock_skus:
            await b2c.send_sku_out_of_stock(
                sku_id=sku.id,
                product_id=sku.product_id,
                available_quantity=0,
            )

    return JSONResponse(
        status_code=200,
        content={
            "order_id": str(request.order_id),
            "status": "RESERVED",
            "reserved_at": reservation.reserved_at.isoformat().replace("+00:00", "Z"),
        },
    )


@router.post("/unreserve")
async def unreserve_inventory(
    payload: dict,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
) -> JSONResponse:
    try:
        request = UnreserveRequest.model_validate(payload)
    except ValidationError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Invalid unreserve payload"},
        )

    if x_service_key is None:
        return JSONResponse(
            status_code=401, content={"code": "UNAUTHORIZED", "message": "Missing service key"}
        )

    existing_stmt = (
        select(InventoryReservation)
        .options(selectinload(InventoryReservation.items))
        .where(InventoryReservation.order_id == request.order_id)
        .limit(1)
    )
    reservation = (await session.execute(existing_stmt)).scalar_one_or_none()
    processed_at = datetime.now(UTC)

    if reservation is None:
        return JSONResponse(
            status_code=200,
            content={
                "order_id": str(request.order_id),
                "status": "UNRESERVED",
                "processed_at": processed_at.isoformat().replace("+00:00", "Z"),
            },
        )

    if reservation.status == InventoryReservationStatus.UNRESERVED:
        effective_at = reservation.processed_at or reservation.reserved_at
        return JSONResponse(
            status_code=200,
            content={
                "order_id": str(reservation.order_id),
                "status": "UNRESERVED",
                "processed_at": effective_at.isoformat().replace("+00:00", "Z"),
            },
        )

    sku_by_id = {}
    for item in reservation.items:
        sku = await session.get(SKU, item.sku_id)
        if sku is not None:
            sku_by_id[item.sku_id] = sku

    for item in reservation.items:
        sku = sku_by_id.get(item.sku_id)
        if sku is None:
            continue
        sku.active_quantity += item.requested
        sku.reserved_quantity -= item.requested

    reservation.status = InventoryReservationStatus.UNRESERVED
    reservation.processed_at = processed_at
    await session.commit()

    return JSONResponse(
        status_code=200,
        content={
            "order_id": str(reservation.order_id),
            "status": "UNRESERVED",
            "processed_at": processed_at.isoformat().replace("+00:00", "Z"),
        },
    )


class FulfillRequest(BaseModel):
    order_id: UUID
    items: list[InventoryItemRequest]


@router.post("/fulfill")
async def fulfill_inventory(
    payload: dict,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
) -> JSONResponse:
    try:
        request = FulfillRequest.model_validate(payload)
    except ValidationError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Invalid fulfill payload"},
        )

    if x_service_key is None:
        return JSONResponse(
            status_code=401, content={"code": "UNAUTHORIZED", "message": "Missing service key"}
        )

    # Idempotency: if this order was already fulfilled, return cached result.
    existing_stmt = (
        select(FulfilledOrder).where(FulfilledOrder.order_id == request.order_id).limit(1)
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        return JSONResponse(
            status_code=200,
            content={
                "order_id": str(existing.order_id),
                "status": "FULFILLED",
                "processed_at": existing.fulfilled_at.isoformat().replace("+00:00", "Z"),
            },
        )

    # Lock rows in consistent order to prevent deadlocks under concurrency.
    sorted_items = sorted(request.items, key=lambda i: i.sku_id)
    sku_ids = [item.sku_id for item in sorted_items]
    stmt = select(SKU).where(SKU.id.in_(sku_ids)).order_by(SKU.id).with_for_update()
    rows = (await session.execute(stmt)).scalars().all()
    by_id = {row.id: row for row in rows}

    for item in request.items:
        if item.sku_id not in by_id:
            return JSONResponse(
                status_code=404,
                content={"code": "SKU_NOT_FOUND", "message": f"SKU {item.sku_id} not found"},
            )
        sku = by_id[item.sku_id]
        if sku.reserved_quantity < item.quantity:
            return JSONResponse(
                status_code=409,
                content={
                    "code": "FULFILL_FAILED",
                    "message": f"SKU {item.sku_id} has insufficient reserved quantity",
                },
            )

    processed_at = datetime.now(UTC)
    for item in request.items:
        sku = by_id[item.sku_id]
        sku.reserved_quantity -= item.quantity
        sku.stock_quantity -= item.quantity

    fulfilled = FulfilledOrder(order_id=request.order_id, fulfilled_at=processed_at)
    session.add(fulfilled)
    await session.commit()

    return JSONResponse(
        status_code=200,
        content={
            "order_id": str(request.order_id),
            "status": "FULFILLED",
            "processed_at": processed_at.isoformat().replace("+00:00", "Z"),
        },
    )
