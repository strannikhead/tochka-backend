from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from b2b.src.products.application.service import ProductsService
from b2b.src.products.dependencies import get_products_service
from b2b.src.products.domain.errors import CategoryNotFoundError
from b2b.src.products.domain.models import ProductListResponse
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/products", tags=["products"])


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
async def get_product(product_id: str) -> dict[str, str]:
    return {"endpoint": "get_product"}


@router.patch("/{product_id}")
async def update_product(product_id: str) -> dict[str, str]:
    return {"endpoint": "update_product"}


@router.delete("/{product_id}")
async def delete_product(product_id: str) -> dict[str, str]:
    return {"endpoint": "delete_product"}


@router.post("/{product_id}/images")
async def add_product_image(product_id: str) -> dict[str, str]:
    return {"endpoint": "add_product_image"}


def _parse_filters(request: Request) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        if not key.startswith("filters[") or not key.endswith("]"):
            continue
        name = key[len("filters[") : -1].strip()
        if not name:
            continue
        filters.setdefault(name, []).append(value)
    return filters


def _to_response(product_list: ProductListResponse) -> dict[str, Any]:
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
