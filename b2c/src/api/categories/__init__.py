from __future__ import annotations

import os
from uuid import UUID

import httpx
from b2c.src.api.catalog.static_data import CATEGORIES, CATEGORY_TREE, category_breadcrumbs
from b2c.src.api.errors import error_response
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/catalog/categories", tags=["Catalog"])
legacy_router = APIRouter(prefix="/api/v1/categories", tags=["categories"], include_in_schema=False)


@router.get("")
async def list_categories() -> list[dict[str, object]]:
    return CATEGORIES


@router.get("/tree")
async def list_categories_tree() -> list[dict[str, object]]:
    return CATEGORY_TREE


@legacy_router.get("")
async def get_categories_tree() -> list[dict[str, object]]:
    return CATEGORY_TREE


@legacy_router.get("/{id}")
async def get_category(id: str) -> object:
    try:
        category_id = UUID(id)
    except ValueError:
        return error_response(400, "Некорректный id категории")

    for category in CATEGORIES:
        if UUID(str(category["id"])) == category_id:
            return category

    return error_response(404, "Категория не найдена")


@legacy_router.get("/{id}/filters")
async def get_category_filters(id: str) -> object:
    base_url = (os.getenv("B2B_BASE_URL") or "http://localhost:8001").rstrip("/")
    url = f"{base_url}/api/v1/categories/{id}/filters"
    headers = {}
    service_key = os.getenv("B2B_SERVICE_KEY")
    if service_key:
        headers["X-Service-Key"] = service_key

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.RequestError:
        return error_response(502, "Unable to reach B2B")

    try:
        payload = response.json()
    except ValueError:
        return error_response(502, "Unexpected upstream response")

    if response.status_code != 200:
        if isinstance(payload, dict) and "code" in payload and "message" in payload:
            return JSONResponse(status_code=response.status_code, content=payload)
        return error_response(response.status_code, "Unexpected upstream response")

    return JSONResponse(content=payload)


@legacy_router.get("/breadcrumbs")
async def get_breadcrumbs(
    category_id: str | None = Query(default=None, include_in_schema=False),
) -> list[dict[str, object]]:
    if category_id is None:
        return category_breadcrumbs()

    try:
        return category_breadcrumbs(UUID(category_id))
    except ValueError:
        return category_breadcrumbs()
