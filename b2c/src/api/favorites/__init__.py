from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from src.api.dependencies import get_current_user_id
from src.api.favorites.dependencies import (
    ProductClient,
    ProductServiceError,
    get_favorites_repository,
    get_favorites_service,
    get_product_client,
)
from src.api.favorites.dependencies import (
    ProductNotFoundError as B2BProductNotFoundError,
)
from src.api.favorites.schemas import DEFAULT_SUBSCRIPTION_EVENTS, SubscribeRequest
from src.api.products.schemas import CatalogProductCardResponse, PaginatedCatalogProductsResponse
from src.favorites.repository import FavoriteRepository
from src.favorites.service import FavoritesService
from src.favorites.service import ProductNotFoundError as FavoriteProductNotFoundError
from src.product_card.repository import UpstreamServiceError

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
        status_code_value = exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=status_code_value, detail=str(exc)) from exc

    return PaginatedCatalogProductsResponse(
        items=[CatalogProductCardResponse.from_domain(product) for product in products],
        total_count=total,
        limit=limit,
        offset=offset,
    )


@router.put("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_to_favorites(
    product_id: str,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    service: Annotated[FavoritesService, Depends(get_favorites_service)],
) -> Response:
    try:
        pid = UUID(product_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        ) from exc

    try:
        await service.add(user_id, pid)
    except FavoriteProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Товар не найден",
        ) from exc
    except UpstreamServiceError as exc:
        status_code_value = exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=status_code_value, detail=str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_favorites(
    product_id: str,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    service: Annotated[FavoritesService, Depends(get_favorites_service)],
) -> Response:
    try:
        pid = UUID(product_id)
    except ValueError:
        # Идемпотентность: невалидный/несуществующий UUID — тот же 204
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    await service.remove(user_id, pid)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{product_id}/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe_to_product(
    product_id: UUID,
    repository: Annotated[FavoriteRepository, Depends(get_favorites_repository)],
    product_client: Annotated[ProductClient, Depends(get_product_client)],
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    payload: SubscribeRequest | None = None,
) -> Response:
    try:
        await product_client.get_product(product_id)
    except B2BProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PRODUCT_NOT_FOUND",
                "message": "Товар с указанным идентификатором не найден",
            },
        ) from exc
    except ProductServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "SERVICE_UNAVAILABLE",
                "message": "Сервис временно недоступен, попробуйте позже",
            },
        ) from exc

    existing_subscription = await repository.get_product_subscription(
        user_id=user_id,
        product_id=product_id,
    )

    if existing_subscription is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    events = payload.events if payload is not None else DEFAULT_SUBSCRIPTION_EVENTS

    await repository.create_product_subscription(
        user_id=user_id,
        product_id=product_id,
        events=[event.value for event in events],
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{product_id}/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe_from_product(
    product_id: UUID,
    repository: Annotated[FavoriteRepository, Depends(get_favorites_repository)],
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> Response:
    await repository.delete_product_subscription(
        user_id=user_id,
        product_id=product_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
