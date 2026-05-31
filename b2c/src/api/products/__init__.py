from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from src.api.products.dependencies import get_product_card_service
from src.product_card.repository import UpstreamServiceError as ProductUpstreamServiceError
from src.product_card.service import ProductCardService

from b2c.src.api.catalog.dependencies import get_catalog_repository
from b2c.src.api.catalog.filters import parse_filters
from b2c.src.api.errors import error_response
from b2c.src.api.products.schemas import (
    CatalogProductDetailResponse,
    ProductShortListResponse,
)
from b2c.src.catalog.repository import CatalogRepository, UpstreamServiceError

base = APIRouter()
SortValue = Literal["price_asc", "price_desc", "popularity", "new"]


@base.get("/", response_model=ProductShortListResponse, response_model_exclude_none=True)
async def list_products(
    request: Request,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category_id: str | None = Query(default=None),
    sort: Annotated[SortValue, Query()] = "popularity",
    q: str | None = Query(default=None),
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
) -> ProductShortListResponse | JSONResponse:
    category_uuid = None
    if category_id is not None:
        try:
            category_uuid = UUID(category_id)
        except ValueError:
            return error_response(400, "INVALID_REQUEST", "Invalid category_id")

    search_value = q

    if search_value is not None:
        trimmed = search_value.strip()
        if trimmed and len(trimmed) < 3:
            return error_response(
                400, "INVALID_REQUEST", "Search query must be at least 3 characters"
            )
        if len(trimmed) > 200:
            return error_response(
                400, "INVALID_REQUEST", "Search query must be at most 200 characters"
            )

    search_for_repo = None
    if search_value is not None:
        search_for_repo = search_value.strip() or None

    try:
        filters = parse_filters(request)
    except ValueError:
        return error_response(400, "INVALID_REQUEST", "Invalid filters format")
    try:
        product_list = await repository.list_products(
            category_id=category_uuid,
            filters=filters,
            sort=sort,
            limit=limit,
            offset=offset,
            search=search_for_repo,
            min_price=min_price,
            max_price=max_price,
        )
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return error_response(status_code, "UPSTREAM_UNAVAILABLE", str(exc))

    return ProductShortListResponse.from_domain(product_list)


@base.get("/{product_id}", response_model=CatalogProductDetailResponse)
async def get_product(
    product_id: str,
    service: Annotated[ProductCardService, Depends(get_product_card_service)],
) -> CatalogProductDetailResponse:
    try:
        parsed_id = UUID(product_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "Некорректный id товара"},
        ) from exc

    try:
        product = await service.get_product_card(parsed_id)
    except ProductUpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": "UPSTREAM_UNAVAILABLE",
                "message": str(exc),
            },
        ) from exc
    if product is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Товар не найден"},
        )

    return CatalogProductDetailResponse.from_domain(product)


@base.get("/{product_id}/similar", include_in_schema=False, response_model=None)
async def get_similar_products(
    product_id: str,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, Any]] | JSONResponse:
    try:
        parsed_id = UUID(product_id)
    except ValueError:
        return error_response(400, "INVALID_REQUEST", "Invalid product_id")

    try:
        products = await repository.get_similar(product_id=parsed_id, limit=limit)
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return error_response(status_code, "UPSTREAM_UNAVAILABLE", str(exc))

    return products


router = APIRouter(prefix="/api/v1/catalog/products", tags=["catalog"])
legacy_router = APIRouter(prefix="/api/v1/products", tags=["catalog"], include_in_schema=False)

router.include_router(base)
legacy_router.include_router(base)
