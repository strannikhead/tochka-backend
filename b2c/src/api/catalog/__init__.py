from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from src.api.products.dependencies import get_product_card_service
from src.product_card.service import ProductCardService

from b2c.src.api.catalog.dependencies import get_banner_repository, get_catalog_repository
from b2c.src.api.catalog.filters import parse_filters
from b2c.src.api.catalog.schemas import BannerResponse, FacetsResponse
from b2c.src.api.catalog.static_data import breadcrumbs
from b2c.src.api.errors import error_response
from b2c.src.api.products.schemas import CatalogProductDetailResponse
from b2c.src.catalog.repository import CatalogRepository, UpstreamServiceError

base = APIRouter()


@base.get("/facets", response_model=FacetsResponse)
async def get_catalog_facets(
    request: Request,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    category_id: str | None = Query(default=None),
) -> FacetsResponse | JSONResponse:
    if category_id is None:
        return error_response(400, "category_id is required")
    try:
        category_uuid = UUID(category_id)
    except ValueError:
        return error_response(400, "Invalid category_id")

    try:
        filters = parse_filters(request, allow_unscoped=True)
    except ValueError:
        return error_response(400, "Invalid filters format")

    try:
        facets = await repository.get_facets(category_id=category_uuid, filters=filters)
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return error_response(status_code, str(exc))

    return FacetsResponse.from_domain(facets)


@base.get("/banners", response_model=list[BannerResponse], response_model_exclude_none=True)
async def get_catalog_banners(
    repository: Annotated[object, Depends(get_banner_repository)],
) -> list[BannerResponse]:
    banners = await repository.list_active(now=datetime.now(UTC))
    return [BannerResponse.from_domain(banner) for banner in banners]


@base.get("/breadcrumbs")
async def get_breadcrumbs(category_id: str | None = None) -> list[dict[str, str]]:
    return breadcrumbs(category_id)


@base.get("/products/{product_id}/similar", include_in_schema=False)
async def get_similar_products(
    product_id: str,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, Any]]:
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


@base.get("/products/{product_id}", response_model=CatalogProductDetailResponse)
async def get_product_detail(
    product_id: str,
    service: Annotated[ProductCardService, Depends(get_product_card_service)],
) -> CatalogProductDetailResponse | JSONResponse:
    try:
        parsed_id = UUID(product_id)
    except ValueError:
        return error_response(400, "Invalid product_id")

    try:
        product = await service.get_product_card(parsed_id)
    except Exception as exc:
        return error_response(502, str(exc))

    if product is None:
        return error_response(404, "Product not found")

    return CatalogProductDetailResponse.from_domain(product)


router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])
legacy_router = APIRouter(prefix="/api/v1", tags=["catalog"], include_in_schema=False)

router.include_router(base)
legacy_router.include_router(base)
