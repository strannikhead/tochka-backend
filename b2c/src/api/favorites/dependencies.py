from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.products.dependencies import get_product_repository
from database import get_db_session
from favorites.repository import DbFavoriteRepository, FavoriteRepository
from favorites.service import FavoritesService
from product_card.repository import ProductRepository


def get_favorite_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FavoriteRepository:
    return DbFavoriteRepository(session)


def get_favorites_service(
    favorite_repo: Annotated[FavoriteRepository, Depends(get_favorite_repository)],
    product_repo: Annotated[ProductRepository, Depends(get_product_repository)],
) -> FavoritesService:
    return FavoritesService(favorite_repo, product_repo)
