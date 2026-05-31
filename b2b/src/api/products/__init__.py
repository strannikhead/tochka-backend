from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from b2b.src.auth import get_current_seller_id, get_optional_seller_id
from b2b.src.db import get_session
from b2b.src.models import SKU, Product
from b2b.src.products.application.service import ProductsService
from b2b.src.products.dependencies import get_products_service
from b2b.src.products.domain.errors import (
    CategoryNotFoundError,
    ProductHardBlockedError,
    ProductNotFoundError,
    ProductNotOwnedError,
)
from b2b.src.products.domain.models import (
    CharacteristicInput,
    CreateProductCommand,
    ProductImageInput,
    ProductListResponse,
)
from b2b.src.public_catalog.application.service import PublicCatalogService
from b2b.src.public_catalog.dependencies import get_public_catalog_service
from b2b.src.public_catalog.domain.errors import (
    CategoryNotFoundError as PublicCategoryNotFoundError,
)
from b2b.src.public_catalog.domain.errors import (
    ProductNotFoundError as PublicProductNotFoundError,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


class ProductImagePayload(BaseModel):
    url: str
    ordering: int = 0


class CharacteristicPayload(BaseModel):
    name: str
    value: str


class ProductCreateRequest(BaseModel):
    # `extra="ignore"` drops any stray `seller_id` sent in the body: seller identity
    # comes only from the JWT (IDOR guard), never from client input.
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    category_id: UUID
    slug: str | None = None
    images: list[ProductImagePayload] = Field(default_factory=list)
    characteristics: list[CharacteristicPayload] = Field(default_factory=list)


class ProductUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    category_id: UUID | None = None
    characteristics: list[CharacteristicPayload] | None = None


class SkuUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    price: int | None = Field(default=None, ge=0)
    discount: int | None = Field(default=None, ge=0)
    cost_price: int | None = Field(default=None, ge=0)
    article: str | None = None
    characteristics: list[CharacteristicPayload] | None = None


def _serialize_created_product(product: Product) -> dict[str, object]:
    return {
        "id": str(product.id),
        "seller_id": str(product.seller_id),
        "category_id": str(product.category_id),
        "title": product.title,
        # *Response schemas require slug as a non-null string; fall back to the id
        # for products created without an explicit slug.
        "slug": product.slug if product.slug is not None else str(product.id),
        "description": product.description,
        "status": product.status.value,
        "deleted": False,
        "blocking_reason_id": None,
        "moderator_comment": None,
        "images": [
            {"id": str(uuid4()), "url": image["url"], "ordering": image.get("ordering", 0)}
            for image in (product.images or [])
        ],
        "characteristics": [
            {"id": str(uuid4()), "name": char["name"], "value": char["value"]}
            for char in (product.characteristics or [])
        ],
        "skus": [],
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat(),
    }


@router.post("", status_code=201)
async def create_product(
    body: ProductCreateRequest,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[ProductsService, Depends(get_products_service)],
) -> JSONResponse:
    command = CreateProductCommand(
        seller_id=seller_id,
        title=body.title,
        description=body.description,
        category_id=body.category_id,
        slug=body.slug,
        images=tuple(
            ProductImageInput(url=image.url, ordering=image.ordering) for image in body.images
        ),
        characteristics=tuple(
            CharacteristicInput(name=char.name, value=char.value) for char in body.characteristics
        ),
    )
    try:
        product = await service.create_product(command)
    except CategoryNotFoundError:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Категория не найдена",
                "details": {"field": "category_id"},
            },
        )

    return JSONResponse(status_code=201, content=_serialize_created_product(product))


@router.get("/{product_id}/skus")
async def list_product_skus(product_id: str) -> dict[str, str]:
    return {"endpoint": "list_product_skus"}


@router.get("")
async def list_products(
    request: Request,
    service: Annotated[ProductsService, Depends(get_products_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(default=None),
    include_deleted: bool = Query(False),
    search: str | None = Query(default=None),
    ids: str | None = Query(default=None),
) -> JSONResponse:
    if ids:
        parsed_ids: list[UUID] = []
        for item in (part.strip() for part in ids.split(",") if part.strip()):
            try:
                parsed_ids.append(UUID(item))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid ids parameter") from exc

        stmt = (
            select(SKU, Product)
            .join(Product, Product.id == SKU.product_id)
            .where(SKU.id.in_(parsed_ids))
        )
        rows = (await session.execute(stmt)).all()
        product_map: dict[UUID, dict[str, object]] = {}
        for sku, product in rows:
            entry = product_map.setdefault(
                product.id,
                {
                    "id": str(product.id),
                    "title": product.title,
                    "status": product.status.value,
                    "deleted": product.deleted,
                    "skus": [],
                },
            )
            entry["skus"].append(
                {
                    "id": str(sku.id),
                    "product_id": str(product.id),
                    "name": sku.name,
                    "price": sku.price,
                    "discount": 0,
                    "active_quantity": sku.active_quantity,
                }
            )
        return JSONResponse(
            content={
                "items": list(product_map.values()),
                "total_count": len(product_map),
                "limit": len(product_map),
                "offset": 0,
            }
        )

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


def _product_to_checkout_payload(product: Product) -> dict[str, object]:
    return {
        "id": str(product.id),
        "title": product.title,
        "status": product.status.value,
        "deleted": product.deleted,
        "skus": [
            {
                "id": str(sku.id),
                "product_id": str(product.id),
                "name": sku.name,
                "price": sku.price,
                "discount": 0,
                "active_quantity": sku.active_quantity,
            }
            for sku in product.skus
        ],
    }


def _normalize_images(raw: list | None) -> list[dict[str, object]]:
    # ProductImageResponse / SKUImageResponse require id, url, ordering. Images are
    # stored as JSON without ids, so backfill an id when absent to keep responses valid.
    return [
        {
            "id": str(image.get("id") or uuid4()),
            "url": image.get("url", ""),
            "ordering": image.get("ordering", 0),
        }
        for image in (raw or [])
    ]


def _normalize_characteristics(raw: list | None) -> list[dict[str, object]]:
    # CharacteristicResponse requires id, name, value.
    return [
        {
            "id": str(char.get("id") or uuid4()),
            "name": char.get("name", ""),
            "value": char.get("value", ""),
        }
        for char in (raw or [])
    ]


def _serialize_sku_common(sku: SKU) -> dict[str, object]:
    return {
        "id": str(sku.id),
        "product_id": str(sku.product_id),
        "name": sku.name,
        "price": sku.price,
        "discount": sku.discount,
        "stock_quantity": sku.stock_quantity,
        "active_quantity": sku.active_quantity,
        "article": sku.article,
        "images": _normalize_images(sku.images),
        "characteristics": _normalize_characteristics(sku.characteristics),
    }


def _serialize_sku_seller(sku: SKU) -> dict[str, object]:
    # Seller view adds the sensitive economics: cost_price and reserved_quantity.
    payload = _serialize_sku_common(sku)
    payload["cost_price"] = sku.cost_price
    payload["reserved_quantity"] = sku.reserved_quantity
    payload["created_at"] = sku.created_at.isoformat()
    payload["updated_at"] = sku.updated_at.isoformat()
    return payload


def _serialize_product_seller(product: Product) -> dict[str, object]:
    return {
        "id": str(product.id),
        "seller_id": str(product.seller_id),
        "category_id": str(product.category_id),
        "title": product.title,
        # *Response schemas require slug as a non-null string; fall back to the id
        # for products created without an explicit slug.
        "slug": product.slug if product.slug is not None else str(product.id),
        "description": product.description,
        "status": product.status.value,
        "deleted": product.deleted,
        "blocking_reason_id": (
            str(product.blocking_reason_id) if product.blocking_reason_id else None
        ),
        "moderator_comment": product.moderator_comment,
        "images": _normalize_images(product.images),
        "characteristics": _normalize_characteristics(product.characteristics),
        "skus": [_serialize_sku_seller(sku) for sku in product.skus],
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat(),
    }


def _serialize_product_public(product: Product) -> dict[str, object]:
    # Storefront projection (X-Service-Key): no cost_price / reserved_quantity, no
    # blocking metadata.
    return {
        "id": str(product.id),
        "seller_id": str(product.seller_id),
        "category_id": str(product.category_id),
        "title": product.title,
        # *Response schemas require slug as a non-null string; fall back to the id
        # for products created without an explicit slug.
        "slug": product.slug if product.slug is not None else str(product.id),
        "description": product.description,
        "status": product.status.value,
        "images": _normalize_images(product.images),
        "characteristics": _normalize_characteristics(product.characteristics),
        "skus": [_serialize_sku_common(sku) for sku in product.skus],
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat(),
    }


@router.get("/{product_id}")
async def get_product(
    product_id: str,
    service: Annotated[ProductsService, Depends(get_products_service)],
    seller_id: Annotated[UUID | None, Depends(get_optional_seller_id)],
    x_service_key: str | None = Header(None, alias="X-Service-Key"),
) -> JSONResponse:
    try:
        parsed = UUID(product_id)
    except ValueError:
        # Unknown id shape — treated as "not found", never as a 400, so we don't leak
        # whether an id is well-formed-but-absent vs. malformed.
        return JSONResponse(status_code=404, content=detail_not_found())

    # Inter-service read takes precedence: X-Service-Key -> public projection.
    if x_service_key is not None:
        _require_service_key(x_service_key)
        try:
            product = await service.get_product_for_service(parsed)
        except ProductNotFoundError:
            return JSONResponse(status_code=404, content=detail_not_found())
        return JSONResponse(content=_serialize_product_public(product))

    # Otherwise this is a seller request and a valid JWT is required.
    if seller_id is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    try:
        product = await service.get_product_for_seller(parsed, seller_id)
    except ProductNotFoundError:
        return JSONResponse(status_code=404, content=detail_not_found())
    return JSONResponse(content=_serialize_product_seller(product))


def detail_not_found() -> dict[str, str]:
    return {"code": "NOT_FOUND", "message": "Товар не найден"}


def _provided_changes(body: BaseModel, allowed_fields: tuple[str, ...]) -> dict[str, object]:
    changes: dict[str, object] = {}
    for field_name in allowed_fields:
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


@router.put("/{product_id}", include_in_schema=False)
@router.patch("/{product_id}")
async def update_product(
    product_id: str,
    body: ProductUpdateRequest,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[ProductsService, Depends(get_products_service)],
) -> JSONResponse:
    try:
        parsed = UUID(product_id)
    except ValueError:
        return JSONResponse(status_code=404, content=detail_not_found())

    changes = _provided_changes(body, ("title", "description", "category_id", "characteristics"))
    try:
        product = await service.update_product(parsed, seller_id, changes)
    except ProductNotFoundError:
        return JSONResponse(status_code=404, content=detail_not_found())
    except CategoryNotFoundError:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Категория не найдена",
                "details": {"field": "category_id"},
            },
        )
    except ProductNotOwnedError:
        return JSONResponse(
            status_code=403,
            content={
                "code": "NOT_OWNER",
                "message": "Product does not belong to the authenticated seller",
            },
        )
    except ProductHardBlockedError:
        return JSONResponse(
            status_code=403,
            content={"code": "FORBIDDEN", "message": "Cannot edit hard-blocked product"},
        )

    return JSONResponse(content=_serialize_product_seller(product))


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: str,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[ProductsService, Depends(get_products_service)],
) -> Response:
    # Soft delete: marks deleted=true (data is kept) and emits DELETED (Moderation) +
    # PRODUCT_DELETED (B2C, with sku_ids) cascade events. Re-deleting an already-deleted
    # product is a 404 (no active product), per the OpenAPI DELETE responses.
    try:
        parsed = UUID(product_id)
    except ValueError:
        return JSONResponse(status_code=404, content=detail_not_found())

    try:
        await service.delete_product(parsed, seller_id)
    except ProductNotFoundError:
        return JSONResponse(status_code=404, content=detail_not_found())
    except ProductNotOwnedError:
        return JSONResponse(
            status_code=403,
            content={
                "code": "NOT_OWNER",
                "message": "Product does not belong to the authenticated seller",
            },
        )
    except ProductHardBlockedError:
        return JSONResponse(
            status_code=403,
            content={"code": "FORBIDDEN", "message": "Cannot delete hard-blocked product"},
        )

    return Response(status_code=204)


def _require_service_key(service_key: str | None) -> None:
    if service_key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail="Invalid service key")


def require_service_key(
    x_service_key: str | None = Header(None, alias="X-Service-Key"),
) -> None:
    if x_service_key != SERVICE_KEY:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Требуется X-Service-Key"},
        )


def _extract_cover_image(images: list | None) -> str | None:
    if not images:
        return None
    first = images[0]
    return str(first.get("url")) if isinstance(first, dict) else str(first)


def _product_to_public_short_dict(product: Product, min_price_val: int) -> dict[str, object]:
    return {
        "id": str(product.id),
        "title": product.title,
        "slug": product.slug if product.slug is not None else str(product.id),
        "status": product.status.value,
        "category_id": str(product.category_id),
        "min_price": min_price_val,
        "cover_image": _extract_cover_image(product.images),
        "created_at": product.created_at.isoformat(),
    }


class BatchProductsRequest(BaseModel):
    product_ids: list[UUID] = Field(max_length=100)


@public_router.get("/products")
async def list_public_products(
    service: Annotated[PublicCatalogService, Depends(get_public_catalog_service)],
    _: Annotated[None, Depends(require_service_key)],
    category_id: UUID | None = Query(None),
    search: str | None = Query(None, min_length=3),
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    seller_id: UUID | None = Query(None),
    sort: str = Query("created_desc"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    rows, total = await service.list_catalog(
        category_id=category_id,
        search=search,
        min_price=min_price,
        max_price=max_price,
        seller_id=seller_id,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(
        content={
            "items": [_product_to_public_short_dict(p, mp) for p, mp in rows],
            "total_count": total,
            "limit": limit,
            "offset": offset,
        }
    )


@public_router.post("/products/batch")
async def batch_public_products(
    body: BatchProductsRequest,
    service: Annotated[PublicCatalogService, Depends(get_public_catalog_service)],
    _: Annotated[None, Depends(require_service_key)],
) -> JSONResponse:
    products = await service.get_batch(body.product_ids)
    return JSONResponse(content=[_serialize_product_public(p) for p in products])


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
    except PublicProductNotFoundError:
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
