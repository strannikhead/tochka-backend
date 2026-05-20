from typing import Annotated, Any
from uuid import UUID

from b2c.src.api.catalog.dependencies import get_catalog_repository
from b2c.src.api.catalog.filters import parse_filters
from b2c.src.api.catalog.schemas import FacetsResponse
from b2c.src.catalog.repository import CatalogRepository, UpstreamServiceError
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/catalog/facets", response_model=FacetsResponse)
async def get_catalog_facets(
    request: Request,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    category_id: str | None = Query(default=None),
) -> FacetsResponse | JSONResponse:
    if category_id is None:
        return JSONResponse(status_code=400, content={"message": "category_id is required"})
    try:
        category_uuid = UUID(category_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid category_id"})

    try:
        filters = parse_filters(request, allow_unscoped=True)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid filters format"})

    try:
        facets = await repository.get_facets(category_id=category_uuid, filters=filters)
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return JSONResponse(status_code=status_code, content={"message": str(exc)})

    return FacetsResponse.from_domain(facets)


@router.get("/breadcrumbs")
async def get_breadcrumbs() -> dict[str, str]:
    return {"endpoint": "get_breadcrumbs"}


@router.get("/catalog/products/{product_id}/similar")
async def get_similar_products(
    product_id: str,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, Any]]:
    try:
        product_uuid = UUID(product_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid product_id"})

    try:
        items = await repository.get_similar(product_id=product_uuid, limit=limit)
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return JSONResponse(status_code=status_code, content={"message": str(exc)})

    return items
