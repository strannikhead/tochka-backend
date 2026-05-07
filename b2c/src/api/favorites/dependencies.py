from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from api.products.dependencies import get_product_repository
from favorites.repository import FavoriteRepository, InMemoryFavoriteRepository
from favorites.service import FavoritesService
from product_card.repository import ProductRepository

_default_repo = InMemoryFavoriteRepository()


def get_favorite_repository() -> FavoriteRepository:
    return _default_repo


def get_favorites_service(
    favorite_repo: Annotated[FavoriteRepository, Depends(get_favorite_repository)],
    product_repo: Annotated[ProductRepository, Depends(get_product_repository)],
) -> FavoritesService:
    return FavoritesService(favorite_repo, product_repo)
