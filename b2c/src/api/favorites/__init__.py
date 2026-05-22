from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from api.dependencies import get_current_user_id
from api.favorites.dependencies import get_favorites_service
from api.products.schemas import CatalogProductCardResponse, PaginatedCatalogProductsResponse
from favorites.service import FavoritesService, ProductNotFoundError
from product_card.repository import UpstreamServiceError

router = APIRouter(prefix="/api/v1/favorites", tags=["favorites"])


@router.get("", response_model=PaginatedCatalogProductsResponse)
async def list_favorites(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    service: Annotated[FavoritesService, Depends(get_favorites_service)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedCatalogProductsResponse:
    try:
        products, total = await service.get_enriched(user_id, limit, offset)
    except UpstreamServiceError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return PaginatedCatalogProductsResponse(
        items=[CatalogProductCardResponse.from_domain(product) for product in products],
        total_count=total,
        limit=limit,
        offset=offset,
    )


@router.put("/{product_id}", status_code=204)
async def add_to_favorites(
    product_id: str,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    service: Annotated[FavoritesService, Depends(get_favorites_service)],
) -> Response:
    try:
        pid = UUID(product_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Товар не найден") from exc

    try:
        await service.add(user_id, pid)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Товар не найден") from exc
    except UpstreamServiceError as exc:
        status_code = exc.status_code or 503
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return Response(status_code=204)


@router.delete("/{product_id}", status_code=204)
async def remove_from_favorites(
    product_id: str,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    service: Annotated[FavoritesService, Depends(get_favorites_service)],
) -> Response:
    try:
        pid = UUID(product_id)
    except ValueError:
        # Идемпотентность: невалидный/несуществующий UUID — тот же 204
        return Response(status_code=204)
    await service.remove(user_id, pid)
    return Response(status_code=204)


@router.post("/{product_id}/subscribe")
async def subscribe_to_product(product_id: str) -> dict[str, str]:
    return {"endpoint": "subscribe_to_product"}
