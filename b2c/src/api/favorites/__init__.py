from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import Response

from api.dependencies import get_current_user_id
from api.favorites.dependencies import get_favorites_service
from api.favorites.schemas import FavoriteMutationResponse, FavoritesListResponse
from favorites.service import FavoritesService
from product_card.repository import UpstreamServiceError

router = APIRouter(prefix="/api/v1/favorites", tags=["favorites"])


@router.get("", response_model=FavoritesListResponse)
async def list_favorites(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    service: Annotated[FavoritesService, Depends(get_favorites_service)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> FavoritesListResponse:
    try:
        items, total = await service.get_enriched(user_id, limit, offset)
    except UpstreamServiceError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return FavoritesListResponse.from_domain(items, total)


@router.post("/{product_id}", status_code=201, response_model=FavoriteMutationResponse)
async def add_to_favorites(
    product_id: str,
    response: Response,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    service: Annotated[FavoritesService, Depends(get_favorites_service)],
) -> FavoriteMutationResponse:
    try:
        pid = UUID(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный product_id") from exc

    entry, created = await service.add(user_id, pid)
    if not created:
        response.status_code = 200
    return FavoriteMutationResponse.from_domain(entry, created)


@router.delete("/{product_id}", status_code=204)
async def remove_from_favorites(
    product_id: str,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    service: Annotated[FavoritesService, Depends(get_favorites_service)],
) -> None:
    try:
        pid = UUID(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный product_id") from exc
    await service.remove(user_id, pid)


@router.post("/{product_id}/subscribe")
async def subscribe_to_product(product_id: str) -> dict[str, str]:
    return {"endpoint": "subscribe_to_product"}
