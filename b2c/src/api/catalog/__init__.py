from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from b2c.src.api.catalog.dependencies import get_catalog_repository
from b2c.src.api.catalog.filters import parse_filters
from b2c.src.api.catalog.schemas import FacetsResponse
from b2c.src.api.catalog.static_data import category_breadcrumbs
from b2c.src.api.errors import error_response
from b2c.src.catalog.repository import CatalogRepository, UpstreamServiceError
from fastapi import APIRouter, Depends, Query, Request

router = APIRouter(prefix="/api/v1", tags=["catalog"], include_in_schema=False)


@router.get("/catalog/facets")
async def get_catalog_facets(
    request: Request,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    category_id: str | None = Query(default=None),
) -> FacetsResponse | dict[str, object]:
    category_value = category_id or request.query_params.get("filter[category_id]")
    if category_value is None:
        return error_response(400, "category_id is required")
    try:
        category_uuid = UUID(category_value)
    except ValueError:
        return error_response(400, "Invalid category_id")

    filters = parse_filters(request, allow_unscoped=True)
    filters.pop("category_id", None)

    try:
        facets = await repository.get_facets(category_id=category_uuid, filters=filters)
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return error_response(status_code, str(exc))

    return FacetsResponse.from_domain(facets)


@router.get("/breadcrumbs")
async def get_breadcrumbs(category_id: str | None = Query(default=None)) -> list[dict[str, object]]:
    if category_id is None:
        return category_breadcrumbs()

    try:
        return category_breadcrumbs(UUID(category_id))
    except ValueError:
        return category_breadcrumbs()


@router.get("/catalog/products/{product_id}/similar")
async def get_similar_products(
    product_id: str,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, Any]] | dict[str, object]:
    try:
        product_uuid = UUID(product_id)
    except ValueError:
        return error_response(400, "Invalid product_id")

    try:
        items = await repository.get_similar(product_id=product_uuid, limit=limit)
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return error_response(status_code, str(exc))

    return items
