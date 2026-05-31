from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse

from b2b.src.public_catalog.application.service import PublicCatalogService
from b2b.src.public_catalog.dependencies import get_public_catalog_service
from b2b.src.public_catalog.domain.errors import (
    CategoryNotFoundError,
    ProductNotFoundError,
)

router = APIRouter(prefix="/api/v1/public/products", tags=["public-catalog"])


@router.get("/{product_id}/similar")
async def get_public_similar_products(
    product_id: str,
    service: Annotated[PublicCatalogService, Depends(get_public_catalog_service)],
    limit: int = Query(10, ge=1, le=50),
    x_service_key: str = Header(..., alias="X-Service-Key"),
) -> JSONResponse:
    try:
        product_uuid = UUID(product_id)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Invalid product_id"},
        )

    try:
        items = await service.get_similar(product_uuid, limit=limit)
    except ProductNotFoundError:
        return JSONResponse(
            status_code=404, content={"code": "NOT_FOUND", "message": "Product not found"}
        )
    except CategoryNotFoundError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Nonexistent category id"},
        )

    return JSONResponse(content=items)


# implementation moved to service
