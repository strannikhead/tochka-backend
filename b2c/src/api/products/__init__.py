from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from b2c.src.api.catalog.dependencies import get_catalog_repository
from b2c.src.api.catalog.filters import parse_filters
from b2c.src.api.catalog.static_data import CATEGORIES, catalog_card
from b2c.src.api.errors import error_response
from b2c.src.api.products.dependencies import get_product_card_service
from b2c.src.api.products.schemas import ProductResponse, ProductShortListResponse
from b2c.src.catalog.repository import CatalogRepository, UpstreamServiceError
from b2c.src.product_card.repository import UpstreamServiceError as ProductUpstreamServiceError
from b2c.src.product_card.service import ProductCardService
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/catalog/products", tags=["Catalog"])
legacy_router = APIRouter(prefix="/api/v1/products", tags=["products"], include_in_schema=False)

ALLOWED_SORTS = ("price_asc", "price_desc", "popularity", "new")


@router.get("")
async def list_catalog_products(
    request: Request,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    sort: str | None = Query(default="popularity"),
    search: str | None = Query(default=None, include_in_schema=False),
    category_id: str | None = Query(default=None, include_in_schema=False),
) -> dict[str, object]:
    product_list_or_error = await _load_product_list(
        request=request,
        repository=repository,
        limit=limit,
        offset=offset,
        search=q or search,
        sort=sort,
        category_id_override=category_id,
    )
    if isinstance(product_list_or_error, JSONResponse):
        return product_list_or_error

    product_list, category_ref = product_list_or_error
    return {
        "items": [
            catalog_card(
                product_id=item.id,
                name=item.title,
                min_price=item.price,
                has_stock=item.in_stock,
                image_url=item.image,
                category_ref=category_ref,
            )
            for item in product_list.items
        ],
        "total_count": product_list.total_count,
        "limit": product_list.limit,
        "offset": product_list.offset,
    }


@legacy_router.get("", response_model=None)
async def list_products(
    request: Request,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category_id: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> ProductShortListResponse | JSONResponse:
    product_list_or_error = await _load_product_list(
        request=request,
        repository=repository,
        limit=limit,
        offset=offset,
        search=search,
        sort=sort,
        category_id_override=category_id,
    )
    if isinstance(product_list_or_error, JSONResponse):
        return product_list_or_error

    product_list, _category_ref = product_list_or_error
    return ProductShortListResponse.from_domain(product_list)


@router.get("/{product_id}")
async def get_catalog_product(
    product_id: str,
    service: Annotated[ProductCardService, Depends(get_product_card_service)],
) -> dict[str, object]:
    try:
        product_uuid = UUID(product_id)
    except ValueError:
        return error_response(400, "Некорректный id товара")

    try:
        product = await service.get_product_card(product_uuid)
    except ProductUpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return error_response(status_code, str(exc))
    if product is None:
        return error_response(404, "Товар не найден")

    return _product_to_catalog_detail(product)


@legacy_router.get("/{id}", response_model=None)
async def get_product(
    id: str,
    service: Annotated[ProductCardService, Depends(get_product_card_service)],
) -> ProductResponse | JSONResponse:
    try:
        product_uuid = UUID(id)
    except ValueError:
        return error_response(400, "Некорректный id товара")

    try:
        product = await service.get_product_card(product_uuid)
    except ProductUpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return error_response(status_code, str(exc))
    if product is None:
        return error_response(404, "Товар не найден")

    return ProductResponse.from_domain(product)


@router.get("/{product_id}/similar", response_model=None)
async def get_similar_products(
    product_id: str,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, object]] | JSONResponse:
    try:
        product_uuid = UUID(product_id)
    except ValueError:
        return error_response(400, "Invalid product_id")

    try:
        items = await repository.get_similar(product_id=product_uuid, limit=limit)
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return error_response(status_code, str(exc))

    return [
        catalog_card(
            product_id=UUID(item["id"]),
            name=str(item.get("name", item.get("title", ""))),
            min_price=int(item.get("min_price", 0)),
            has_stock=bool(item.get("has_stock", False)),
            image_url=_first_image_url(item),
            category_ref=CATEGORIES[0],
        )
        for item in items
    ]


@legacy_router.get("/{id}/similar")
async def get_legacy_similar_products(id: str) -> dict[str, str]:
    return {"endpoint": "get_similar_products"}


@legacy_router.get("/{product_id}/skus")
async def list_product_skus(product_id: str) -> dict[str, str]:
    return {"endpoint": "list_product_skus"}


@legacy_router.get("/{product_id}/skus/{sku_id}")
async def get_product_sku(product_id: str, sku_id: str) -> dict[str, str]:
    return {"endpoint": "get_product_sku"}


async def _load_product_list(
    *,
    request: Request,
    repository: CatalogRepository,
    limit: int,
    offset: int,
    search: str | None,
    sort: str | None,
    category_id_override: str | None,
) -> tuple[Any, dict[str, object]] | JSONResponse:
    query_filters = parse_filters(request, allow_unscoped=True)
    category_values = query_filters.pop("category_id", [])
    category_value = category_id_override or (category_values[-1] if category_values else None)
    category_ref = _category_ref(category_value)

    category_uuid = None
    if category_value is not None:
        try:
            category_uuid = UUID(category_value)
        except ValueError:
            return error_response(400, "Invalid category_id")

    sort_value = sort or "popularity"
    if sort_value not in ALLOWED_SORTS:
        allowed = ", ".join(ALLOWED_SORTS)
        return error_response(400, f"Invalid sort parameter. Allowed values: {allowed}")

    if search is not None and len(search) > 200:
        return error_response(400, "Search query is too long")

    try:
        product_list = await repository.list_products(
            category_id=category_uuid,
            filters=query_filters,
            sort=sort_value,
            limit=limit,
            offset=offset,
            search=search,
        )
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return error_response(status_code, str(exc))

    return product_list, category_ref


def _category_ref(category_value: str | None) -> dict[str, object]:
    if category_value is None:
        return CATEGORIES[0]
    try:
        category_uuid = UUID(category_value)
    except ValueError:
        return {
            "id": category_value,
            "name": "Category",
            "parent_id": None,
            "level": 0,
            "path": ["Category"],
        }

    for category in CATEGORIES:
        if UUID(str(category["id"])) == category_uuid:
            return category

    return {
        "id": str(category_uuid),
        "name": "Category",
        "parent_id": None,
        "level": 0,
        "path": ["Category"],
    }


def _product_to_catalog_detail(product: Any) -> dict[str, object]:
    images = [
        {
            "id": str(image.id),
            "url": image.url,
            "ordering": image.ordering,
            "alt": image.alt or "",
            "is_main": bool(image.is_main) if image.is_main is not None else index == 0,
        }
        for index, image in enumerate(product.images)
    ]

    skus = []
    for sku in product.skus:
        sku_images = [
            {
                "id": str(image.id),
                "url": image.url,
                "ordering": image.ordering,
                "alt": image.alt or "",
                "is_main": bool(image.is_main) if image.is_main is not None else index == 0,
            }
            for index, image in enumerate(sku.images)
        ]
        skus.append(
            {
                "id": str(sku.id),
                "name": sku.name,
                "sku_code": sku.sku_code,
                "price": sku.price,
                "old_price": sku.price + sku.discount if sku.discount else None,
                "available_quantity": sku.available_quantity,
                "attributes": {
                    characteristic.name: characteristic.value
                    for characteristic in sku.characteristics
                },
                "images": sku_images,
            }
        )

    return {
        "id": str(product.id),
        "name": product.name,
        "slug": product.slug,
        "category": CATEGORIES[0],
        "min_price": product.min_price or min((sku.price for sku in product.skus), default=0),
        "old_price": None,
        "has_stock": any(sku.available_quantity > 0 for sku in product.skus),
        "rating": 4.8,
        "reviews_count": 0,
        "images": images,
        "seller": {
            "id": "33333333-3333-4333-8333-333333333333",
            "display_name": "NeoMarket",
        },
        "description": product.description,
        "attributes": {
            characteristic.name: characteristic.value for characteristic in product.characteristics
        },
        "skus": skus,
    }


def _first_image_url(item: dict[str, Any]) -> str | None:
    images = item.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            url = first.get("url")
            if url is not None:
                return str(url)
    return None
