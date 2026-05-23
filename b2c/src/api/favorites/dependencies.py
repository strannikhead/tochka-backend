from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.products.dependencies import get_product_repository
from src.database import get_session
from src.favorites.repository import DbFavoriteRepository, FavoriteRepository
from src.favorites.service import FavoritesService
from src.product_card.repository import ProductRepository


def get_favorite_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FavoriteRepository:
    return DbFavoriteRepository(session)


def get_favorites_service(
    favorite_repo: Annotated[FavoriteRepository, Depends(get_favorite_repository)],
    product_repo: Annotated[ProductRepository, Depends(get_product_repository)],
) -> FavoritesService:
    return FavoritesService(favorite_repo, product_repo)
