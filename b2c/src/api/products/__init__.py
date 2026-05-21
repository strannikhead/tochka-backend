from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from b2c.src.api.catalog.dependencies import get_catalog_repository
from b2c.src.api.catalog.filters import parse_filters
from b2c.src.api.products.dependencies import get_product_card_service
from b2c.src.api.products.schemas import (
    CatalogProductCardResponse,
    CatalogProductDetailResponse,
    ProductShortListResponse,
)
from b2c.src.catalog.repository import CatalogRepository, UpstreamServiceError
from b2c.src.product_card.repository import UpstreamServiceError as ProductUpstreamServiceError
from b2c.src.product_card.service import ProductCardService

router = APIRouter(prefix="/api/v1/products", tags=["catalog"])
ALLOWED_SORTS = (
    "rating",
    "popularity",
    "price_asc",
    "price_desc",
    "date_desc",
    "discount_desc",
)


@router.get("", response_model=ProductShortListResponse)
async def list_products(
    request: Request,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category_id: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> ProductShortListResponse | JSONResponse:
    category_uuid = None
    if category_id is not None:
        try:
            category_uuid = UUID(category_id)
        except ValueError:
            return JSONResponse(status_code=400, content={"message": "Invalid category_id"})

    if sort is not None and sort not in ALLOWED_SORTS:
        allowed = ", ".join(ALLOWED_SORTS)
        return JSONResponse(
            status_code=400,
            content={"message": f"Invalid sort parameter. Allowed values: {allowed}"},
        )

    if search is not None:
        trimmed = search.strip()
        if trimmed and len(trimmed) < 3:
            return JSONResponse(
                status_code=400,
                content={
                    "code": "INVALID_REQUEST",
                    "message": "Search query must be at least 3 characters",
                },
            )
        if len(trimmed) > 200:
            return JSONResponse(
                status_code=400,
                content={
                    "code": "INVALID_REQUEST",
                    "message": "Search query must be at most 200 characters",
                },
            )

    # normalize search for repository call: use trimmed string or None
    search_for_repo = None
    if search is not None:
        search_for_repo = search.strip() or None

    try:
        filters = parse_filters(request)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid filters format"})
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
        return JSONResponse(status_code=status_code, content={"message": str(exc)})

    return ProductShortListResponse.from_domain(product_list)


@router.get("/{product_id}", response_model=CatalogProductDetailResponse)
async def get_product(
    product_id: str,
    service: Annotated[ProductCardService, Depends(get_product_card_service)],
) -> CatalogProductDetailResponse:
    try:
        parsed_id = UUID(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id товара") from exc

    try:
        product = await service.get_product_card(parsed_id)
    except ProductUpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")

    return CatalogProductDetailResponse.from_domain(product)


@router.get("/{product_id}/similar", response_model=list[CatalogProductCardResponse])
async def get_similar_products(
    product_id: str,
    service: Annotated[ProductCardService, Depends(get_product_card_service)],
    limit: int = 10,
) -> list[CatalogProductCardResponse]:
    try:
        parsed_id = UUID(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id товара") from exc

    try:
        products = await service.get_similar_products(parsed_id, limit=limit)
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return [CatalogProductCardResponse.from_domain(product) for product in products]
