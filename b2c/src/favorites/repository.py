from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from favorites.domain import FavoriteEntry


class FavoriteRepository(Protocol):
    async def get_user_favorites(self, user_id: UUID) -> list[FavoriteEntry]: ...
    async def add_favorite(self, user_id: UUID, product_id: UUID) -> tuple[FavoriteEntry, bool]: ...
    async def remove_favorite(self, user_id: UUID, product_id: UUID) -> None: ...


class InMemoryFavoriteRepository:
    def __init__(self) -> None:
        self._data: dict[tuple[UUID, UUID], FavoriteEntry] = {}

    async def get_user_favorites(self, user_id: UUID) -> list[FavoriteEntry]:
        return [e for e in self._data.values() if e.user_id == user_id]

    async def add_favorite(self, user_id: UUID, product_id: UUID) -> tuple[FavoriteEntry, bool]:
        key = (user_id, product_id)
        if key in self._data:
            return self._data[key], False
        entry = FavoriteEntry(user_id=user_id, product_id=product_id, added_at=datetime.now(UTC))
        self._data[key] = entry
        return entry, True

    async def remove_favorite(self, user_id: UUID, product_id: UUID) -> None:
        self._data.pop((user_id, product_id), None)
