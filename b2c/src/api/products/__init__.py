from typing import Annotated
from uuid import UUID

from b2c.src.api.catalog.dependencies import get_catalog_repository
from b2c.src.api.catalog.filters import parse_filters
from b2c.src.api.products.dependencies import get_product_card_service
from b2c.src.api.products.schemas import ProductResponse, ProductShortListResponse
from b2c.src.catalog.repository import CatalogRepository, UpstreamServiceError
from b2c.src.product_card.repository import UpstreamServiceError as ProductUpstreamServiceError
from b2c.src.product_card.service import ProductCardService
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/catalog/products", tags=["products"])

ALLOWED_SORTS = (
    "rating",
    "popularity",
    "price_asc",
    "price_desc",
    "date_desc",
    "discount_desc",
)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})


@router.get("", response_model=ProductShortListResponse)
async def list_products(
    request: Request,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category_id: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> ProductShortListResponse | JSONResponse:
    category_uuid = None
    if category_id is not None:
        try:
            category_uuid = UUID(category_id)
        except ValueError:
            return _error(400, "INVALID_REQUEST", "Invalid category_id")

    if sort is not None and sort not in ALLOWED_SORTS:
        allowed = ", ".join(ALLOWED_SORTS)
        return _error(
            400,
            "INVALID_REQUEST",
            f"Invalid sort parameter. Allowed values: {allowed}",
        )

    if q is not None:
        trimmed = q.strip()
        if trimmed and len(trimmed) < 3:
            return _error(400, "INVALID_REQUEST", "Search query must be at least 3 characters")
        if len(trimmed) > 200:
            return _error(400, "INVALID_REQUEST", "Search query must be at most 200 characters")

    # normalize search for repository call: use trimmed string or None
    search_for_repo = None
    if q is not None:
        search_for_repo = q.strip() or None

    try:
        filters = parse_filters(request)
    except ValueError:
        return _error(400, "INVALID_REQUEST", "Invalid filters format")
    try:
        product_list = await repository.list_products(
            category_id=category_uuid,
            filters=filters,
            sort=sort,
            limit=limit,
            offset=offset,
            search=search_for_repo,
        )
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return _error(status_code, "UPSTREAM_ERROR", str(exc))

    return ProductShortListResponse.from_domain(product_list)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    service: Annotated[ProductCardService, Depends(get_product_card_service)],
) -> ProductResponse | JSONResponse:
    try:
        product_uuid = UUID(product_id)
    except ValueError:
        return _error(400, "INVALID_REQUEST", "Некорректный id товара")

    try:
        product = await service.get_product_card(product_uuid)
    except ProductUpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return _error(status_code, "UPSTREAM_ERROR", str(exc))
    if product is None:
        return _error(404, "NOT_FOUND", "Товар не найден")

    return ProductResponse.from_domain(product)
