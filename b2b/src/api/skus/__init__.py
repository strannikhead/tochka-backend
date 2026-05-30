from typing import Annotated
from uuid import UUID

from b2b.src.api.products import SkuUpdateRequest, _serialize_sku_seller
from b2b.src.auth import get_current_seller_id
from b2b.src.products.application.service import ProductsService
from b2b.src.products.dependencies import get_products_service
from b2b.src.products.domain.errors import (
    ProductHardBlockedError,
    SkuNotFoundError,
    SkuNotOwnedError,
)
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/skus", tags=["skus"])


@router.post("")
async def create_sku() -> dict[str, str]:
    return {"endpoint": "create_sku"}


@router.get("/{sku_id}")
async def get_sku(sku_id: str) -> dict[str, str]:
    return {"endpoint": "get_sku"}


def _provided_changes(body: SkuUpdateRequest) -> dict[str, object]:
    changes: dict[str, object] = {}
    for field_name in ("name", "price", "discount", "cost_price", "article", "characteristics"):
        if field_name not in body.model_fields_set:
            continue
        value = getattr(body, field_name)
        if isinstance(value, list):
            changes[field_name] = [
                item.model_dump() if hasattr(item, "model_dump") else item for item in value
            ]
        else:
            changes[field_name] = value
    return changes


@router.put("/{sku_id}", include_in_schema=False)
@router.patch("/{sku_id}")
async def update_sku(
    sku_id: str,
    body: SkuUpdateRequest,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[ProductsService, Depends(get_products_service)],
) -> JSONResponse:
    try:
        parsed = UUID(sku_id)
    except ValueError:
        return JSONResponse(
            status_code=404,
            content={"code": "NOT_FOUND", "message": "SKU not found"},
        )

    try:
        sku = await service.update_sku(parsed, seller_id, _provided_changes(body))
    except SkuNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"code": "NOT_FOUND", "message": "SKU not found"},
        )
    except SkuNotOwnedError:
        return JSONResponse(
            status_code=403,
            content={
                "code": "NOT_OWNER",
                "message": "SKU does not belong to the authenticated seller",
            },
        )
    except ProductHardBlockedError:
        return JSONResponse(
            status_code=403,
            content={"code": "FORBIDDEN", "message": "Cannot edit hard-blocked product"},
        )

    return JSONResponse(content=_serialize_sku_seller(sku))


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
