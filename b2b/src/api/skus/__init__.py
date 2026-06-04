from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from b2b.src.auth import get_current_seller_id
from b2b.src.config import get_settings
from b2b.src.db import get_session
from b2b.src.skus.application.service import SkuService
from b2b.src.skus.domain.errors import (
    ProductAccessDeniedError,
    ProductHardBlockedError,
    ProductNotFoundError,
)
from b2b.src.skus.infrastructure.moderation_client import ModerationClient

router = APIRouter(prefix="/api/v1/skus", tags=["skus"])


class SKUImageCreate(BaseModel):
    url: str
    ordering: int = 0


class CharacteristicCreate(BaseModel):
    name: str
    value: str


class SKUCreateRequest(BaseModel):
    product_id: UUID
    name: str = Field(min_length=1, max_length=255)
    price: int = Field(ge=0)
    discount: int = Field(default=0, ge=0)
    cost_price: int | None = Field(default=None, gt=0)
    article: str | None = None
    images: list[SKUImageCreate] = Field(default_factory=list)
    characteristics: list[CharacteristicCreate] = Field(default_factory=list)


def _get_sku_service(session: Annotated[AsyncSession, Depends(get_session)]) -> SkuService:
    settings = get_settings()
    client = ModerationClient(
        base_url=settings.moderation.url,
        service_key=settings.moderation.service_key,
    )
    return SkuService(session, client)


def _serialize_sku(sku) -> dict:
    return {
        "id": str(sku.id),
        "product_id": str(sku.product_id),
        "name": sku.name,
        "price": sku.price,
        "discount": sku.discount,
        "cost_price": sku.cost_price,
        "stock_quantity": sku.stock_quantity,
        "active_quantity": sku.active_quantity,
        "reserved_quantity": sku.reserved_quantity,
        "article": sku.article,
        "images": [
            {
                "id": str(img.get("id") or uuid4()),
                "url": img["url"],
                "ordering": img.get("ordering", 0),
            }
            for img in (sku.images or [])
        ],
        "characteristics": [
            {"id": str(c.get("id") or uuid4()), "name": c["name"], "value": c["value"]}
            for c in (sku.characteristics or [])
        ],
        "created_at": sku.created_at.isoformat(),
        "updated_at": sku.updated_at.isoformat(),
    }


@router.post("", status_code=201)
async def create_sku(
    body: SKUCreateRequest,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[SkuService, Depends(_get_sku_service)],
) -> JSONResponse:
    try:
        sku = await service.create_sku(
            product_id=body.product_id,
            seller_id=seller_id,
            name=body.name,
            price=body.price,
            discount=body.discount,
            cost_price=body.cost_price,
            article=body.article,
            images=[{"url": img.url, "ordering": img.ordering} for img in body.images],
            characteristics=[{"name": c.name, "value": c.value} for c in body.characteristics],
        )
    except ProductNotFoundError, ProductAccessDeniedError, ProductHardBlockedError:
        return JSONResponse(
            status_code=403,
            content={"code": "FORBIDDEN", "message": "Нет доступа к товару"},
        )
    return JSONResponse(status_code=201, content=_serialize_sku(sku))


@router.get("/{sku_id}")
async def get_sku(sku_id: str) -> dict[str, str]:
    return {"endpoint": "get_sku"}


@router.patch("/{sku_id}")
async def update_sku(sku_id: str) -> dict[str, str]:
    return {"endpoint": "update_sku"}


@router.delete("/{sku_id}")
async def delete_sku(sku_id: str) -> dict[str, str]:
    return {"endpoint": "delete_sku"}


@router.post("/images")
async def add_sku_image() -> dict[str, str]:
    return {"endpoint": "add_sku_image"}


@router.patch("/images/{image_id}")
async def update_sku_image(image_id: str) -> dict[str, str]:
    return {"endpoint": "update_sku_image"}


@router.delete("/images/{image_id}")
async def delete_sku_image(image_id: str) -> dict[str, str]:
    return {"endpoint": "delete_sku_image"}
