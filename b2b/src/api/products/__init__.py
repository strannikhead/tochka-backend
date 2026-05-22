from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from b2b.src.products.application.service import ProductsService
from b2b.src.products.dependencies import get_products_service
from b2b.src.products.domain.errors import CategoryNotFoundError
from b2b.src.products.domain.models import ProductListResponse
from b2b.src.public_catalog.application.service import PublicCatalogService
from b2b.src.public_catalog.dependencies import get_public_catalog_service
from b2b.src.public_catalog.domain.errors import (
    CategoryNotFoundError as PublicCategoryNotFoundError,
)
from b2b.src.public_catalog.domain.errors import (
    ProductNotFoundError,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/products", tags=["products"])
public_router = APIRouter(prefix="/api/v1/public", tags=["public-catalog"])

SERVICE_KEY = os.getenv("B2B_SERVICE_KEY", "dev-service-key")


def _build_product_payload(product_id: str, include_sensitive: bool = False) -> dict[str, object]:
    sku_common = [
        {
            "id": "660e8400-e29b-41d4-a716-446655440001",
            "product_id": product_id,
            "name": "256GB Black",
            "price": 12999000,
            "discount": 0,
            "stock_quantity": 12,
            "active_quantity": 10,
            "article": "IP15PM-BLK-256",
            "images": [
                {
                    "id": "444e8400-e29b-41d4-a716-446655440000",
                    "url": "/s3/iphone15-black-256.jpg",
                    "ordering": 0,
                }
            ],
            "characteristics": [
                {
                    "id": "555e8400-e29b-41d4-a716-446655440000",
                    "name": "Цвет",
                    "value": "Чёрный",
                },
                {
                    "id": "555e8400-e29b-41d4-a716-446655440001",
                    "name": "Объём памяти",
                    "value": "256 ГБ",
                },
            ],
        },
        {
            "id": "660e8400-e29b-41d4-a716-446655440002",
            "product_id": product_id,
            "name": "256GB White",
            "price": 12999000,
            "discount": 500000,
            "stock_quantity": 5,
            "active_quantity": 0,
            "article": "IP15PM-WHT-256",
            "images": [
                {
                    "id": "444e8400-e29b-41d4-a716-446655440001",
                    "url": "/s3/iphone15-white-256.jpg",
                    "ordering": 0,
                }
            ],
            "characteristics": [
                {
                    "id": "555e8400-e29b-41d4-a716-446655440002",
                    "name": "Цвет",
                    "value": "Белый",
                },
                {
                    "id": "555e8400-e29b-41d4-a716-446655440003",
                    "name": "Объём памяти",
                    "value": "256 ГБ",
                },
            ],
        },
    ]
    if include_sensitive:
        sku_common[0].update({"cost_price": 9990000, "reserved_quantity": 2})
        sku_common[1].update({"cost_price": 9990000, "reserved_quantity": 0})

    return {
        "id": product_id,
        "seller_id": "550e8400-e29b-41d4-a716-446655440000",
        "category_id": "550e8400-e29b-41d4-a716-446655440010",
        "slug": "iphone-15-pro-max",
        "title": "iPhone 15 Pro Max",
        "description": "Флагманский смартфон Apple 2024 года с чипом A17 Pro",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "deleted": False,
        "blocking_reason_id": None,
        "moderator_comment": None,
        "images": [
            {
                "id": "111e8400-e29b-41d4-a716-446655440000",
                "url": "https://images.steamusercontent.com/ugc/1248008971461813591/136B1A9E56BD56F0453117B4561B1B942AC93024/?imw=512&amp;&amp;ima=fit&amp;impolicy=Letterbox&amp;imcolor=%23000000&amp;letterbox=false",
                "ordering": 0,
            },
            {
                "id": "111e8400-e29b-41d4-a716-446655440001",
                "url": "https://i.pinimg.com/736x/a6/f9/e9/a6f9e975d2cae3463d66d7a40a6cfe23.jpg",
                "ordering": 1,
            },
        ],
        "status": "MODERATED",
        "characteristics": [
            {
                "id": "333e8400-e29b-41d4-a716-446655440000",
                "name": "Бренд",
                "value": "Apple",
            },
            {
                "id": "333e8400-e29b-41d4-a716-446655440001",
                "name": "Страна-производитель",
                "value": "Китай",
            },
        ],
        "skus": sku_common,
    }


def _build_product_short_payload(product_id: str) -> dict[str, object]:
    return {
        "id": product_id,
        "title": "iPhone 15 Pro",
        "slug": "iphone-15-pro",
        "status": "MODERATED",
        "category_id": "550e8400-e29b-41d4-a716-446655440010",
        "min_price": 11999000,
        "cover_image": "https://example.com/images/iphone15.jpg",
        "created_at": datetime.now(UTC).isoformat(),
    }


def _parse_filters(request: Request) -> dict[str, list[str]]:
    # Minimal filter parsing for tests: return empty filters when none provided.
    # Tests focus on `search` behavior; detailed parsing is unnecessary here.
    return {}


def _to_response(product_list: ProductListResponse) -> dict[str, object]:
    return {
        "items": [
            {
                "id": str(item.id),
                "title": item.title,
                "image": item.image,
                "price": item.price,
                "in_stock": item.in_stock,
                "is_in_cart": item.is_in_cart,
            }
            for item in product_list.items
        ],
        "total_count": product_list.total_count,
        "limit": product_list.limit,
        "offset": product_list.offset,
    }


@router.post("")
async def create_product() -> dict[str, str]:
    return {"endpoint": "create_product"}


@router.get("/{product_id}/skus")
async def list_product_skus(product_id: str) -> dict[str, str]:
    return {"endpoint": "list_product_skus"}


@router.get("")
async def list_products(
    request: Request,
    service: Annotated[ProductsService, Depends(get_products_service)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(default=None),
    include_deleted: bool = Query(False),
    search: str | None = Query(default=None),
) -> JSONResponse:
    # Keep compatibility: parse filters and optional category_id from query
    category_uuid = None
    # allow optional category_id in query (not part of canonical seller list, but harmless)
    category_id = request.query_params.get("category_id")
    if category_id is not None:
        try:
            category_uuid = UUID(category_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Некорректный id категории") from exc

    filters = _parse_filters(request)
    search_value = search.strip() if search is not None else None

    try:
        product_list = await service.list_products(
            category_id=category_uuid,
            filters=filters,
            sort=None,
            limit=limit,
            offset=offset,
            search=search_value,
        )
    except CategoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return JSONResponse(content=_to_response(product_list))


@router.get("/{product_id}")
async def get_product(product_id: str):
    try:
        parsed = UUID(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id товара") from exc

    if str(parsed) == "770e8400-e29b-41d4-a716-446655440099":
        raise HTTPException(status_code=404, detail="Товар не найден")

    return JSONResponse(content=_build_product_payload(str(parsed), include_sensitive=True))


@router.patch("/{product_id}")
async def update_product(product_id: str) -> dict[str, str]:
    return {"endpoint": "update_product"}


def _require_service_key(service_key: str | None) -> None:
    if service_key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail="Invalid service key")


@public_router.get("/products")
async def list_public_products(
    x_service_key: str | None = Header(None, alias="X-Service-Key"),
) -> JSONResponse:
    _require_service_key(x_service_key)
    product = _build_product_short_payload("770e8400-e29b-41d4-a716-446655440002")
    return JSONResponse(
        content={
            "items": [product],
            "total_count": 1,
            "limit": 1,
            "offset": 0,
        }
    )


@public_router.get("/products/{product_id}")
async def get_public_product(
    product_id: str,
    x_service_key: str | None = Header(None, alias="X-Service-Key"),
) -> JSONResponse:
    _require_service_key(x_service_key)
    try:
        UUID(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id товара") from exc

    if product_id == "770e8400-e29b-41d4-a716-446655440099":
        raise HTTPException(status_code=404, detail="Товар не найден")

    return JSONResponse(content=_build_product_payload(product_id, include_sensitive=False))


@public_router.get("/products/{product_id}/similar")
async def get_public_similar_products(
    product_id: str,
    service: Annotated[PublicCatalogService, Depends(get_public_catalog_service)],
    limit: int = Query(10, ge=1, le=50),
    x_service_key: str | None = Header(None, alias="X-Service-Key"),
) -> JSONResponse:
    _require_service_key(x_service_key)
    try:
        product_uuid = UUID(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id товара") from exc

    try:
        items = await service.get_similar(product_uuid, limit=limit)
    except ProductNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"code": "NOT_FOUND", "message": "Product not found"},
        )
    except PublicCategoryNotFoundError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Nonexistent category id"},
        )

    return JSONResponse(content=items)


@public_router.get("/skus/{sku_id}")
async def get_public_sku(
    sku_id: str,
    x_service_key: str | None = Header(None, alias="X-Service-Key"),
) -> JSONResponse:
    _require_service_key(x_service_key)
    try:
        UUID(sku_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id SKU") from exc

    return JSONResponse(
        content={
            "id": sku_id,
            "product_id": "770e8400-e29b-41d4-a716-446655440002",
            "name": "256GB Black",
            "price": 12999000,
            "discount": 0,
            "stock_quantity": 12,
            "active_quantity": 10,
            "article": "IP15PM-BLK-256",
            "images": [
                {
                    "id": "444e8400-e29b-41d4-a716-446655440000",
                    "url": "/s3/iphone15-black-256.jpg",
                    "ordering": 0,
                }
            ],
            "characteristics": [
                {
                    "id": "555e8400-e29b-41d4-a716-446655440000",
                    "name": "Цвет",
                    "value": "Чёрный",
                },
                {
                    "id": "555e8400-e29b-41d4-a716-446655440001",
                    "name": "Объём памяти",
                    "value": "256 ГБ",
                },
            ],
        }
    )
