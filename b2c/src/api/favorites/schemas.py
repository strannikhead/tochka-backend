from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from api.products.schemas import ProductResponse
from favorites.domain import FavoriteEntry
from product_card.domain import Product


class FavoriteMutationResponse(BaseModel):
    product_id: UUID
    user_id: UUID
    added_at: datetime
    message: str

    @classmethod
    def from_domain(cls, entry: FavoriteEntry, created: bool) -> FavoriteMutationResponse:
        msg = "Товар добавлен в избранное" if created else "Товар уже находится в избранном"
        return cls(
            product_id=entry.product_id,
            user_id=entry.user_id,
            added_at=entry.added_at,
            message=msg,
        )


class FavoriteItemResponse(BaseModel):
    product: ProductResponse
    added_at: datetime


class FavoritesListResponse(BaseModel):
    items: list[FavoriteItemResponse]
    total: int

    @classmethod
    def from_domain(
        cls,
        items: list[tuple[FavoriteEntry, Product]],
        total: int,
    ) -> FavoritesListResponse:
        return cls(
            items=[
                FavoriteItemResponse(
                    product=ProductResponse.from_domain(product),
                    added_at=entry.added_at,
                )
                for entry, product in items
            ],
            total=total,
        )
