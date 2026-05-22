from __future__ import annotations

from uuid import UUID

from b2c.src.api.catalog.static_data import BANNERS, COLLECTIONS
from b2c.src.api.errors import error_response
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/catalog", tags=["Catalog"])
legacy_router = APIRouter(prefix="/api/v1", tags=["home"], include_in_schema=False)


@router.get("/banners")
async def get_catalog_banners() -> list[dict[str, object]]:
    return BANNERS


@router.get("/collections")
async def get_catalog_collections() -> list[dict[str, object]]:
    return COLLECTIONS


@legacy_router.get("/home/banners")
async def get_home_banners() -> list[dict[str, object]]:
    return BANNERS


@legacy_router.post("/banner-events")
async def post_banner_events() -> dict[str, str]:
    return {"endpoint": "post_banner_events"}


@legacy_router.get("/main/collections")
async def get_collections() -> list[dict[str, object]]:
    return COLLECTIONS


@legacy_router.get("/collections/{collection_id}/products")
async def get_collection_products(
    collection_id: str,
) -> list[dict[str, object]] | dict[str, object]:
    for collection in COLLECTIONS:
        if collection.get("id") == collection_id:
            return list(collection.get("products", []))
    try:
        UUID(collection_id)
    except ValueError:
        return error_response(400, "Invalid collection_id")
    return error_response(404, "Collection not found")
