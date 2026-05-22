from __future__ import annotations

from uuid import UUID

from b2c.src.api.errors import error_response
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/favorites", tags=["Favorites"])
legacy_router = APIRouter(prefix="/api/v1/favorites", tags=["favorites"], include_in_schema=False)

_FAVORITES: set[str] = set()


@router.get("")
async def list_favorites(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, object]:
    return {"items": [], "total_count": 0, "limit": limit, "offset": offset}


@router.put("/{product_id}", status_code=204)
async def add_to_favorites(product_id: str) -> None:
    try:
        UUID(product_id)
    except ValueError:
        return error_response(400, "Invalid product_id")
    _FAVORITES.add(product_id)


@router.delete("/{product_id}", status_code=204)
async def remove_from_favorites(product_id: str) -> None:
    _FAVORITES.discard(product_id)


@router.post("/{product_id}/subscribe", status_code=204)
async def subscribe_to_product(product_id: str) -> None:
    try:
        UUID(product_id)
    except ValueError:
        return error_response(400, "Invalid product_id")


@legacy_router.get("")
async def list_legacy_favorites(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, object]:
    return await list_favorites(limit=limit, offset=offset)


@legacy_router.post("/{product_id}", status_code=204)
async def add_to_legacy_favorites(product_id: str) -> None:
    return await add_to_favorites(product_id)


@legacy_router.delete("/{product_id}", status_code=204)
async def remove_from_legacy_favorites(product_id: str) -> None:
    return await remove_from_favorites(product_id)


@legacy_router.post("/{product_id}/subscribe", status_code=204)
async def subscribe_to_legacy_product(product_id: str) -> None:
    return await subscribe_to_product(product_id)
