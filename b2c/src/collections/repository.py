from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.collections.domain import CollectionStored

if TYPE_CHECKING:
    from src.models import Collection as CollectionModel


def _to_domain(row: CollectionModel) -> CollectionStored:
    raw_ids = row.product_ids or []
    return CollectionStored(
        id=row.id,
        name=row.title,
        description=row.description,
        product_ids=tuple(UUID(str(pid)) for pid in raw_ids),
        ordering=row.ordering,
    )


class CollectionRepository(Protocol):
    async def list_active(self) -> list[CollectionStored]: ...


class InMemoryCollectionRepository:
    def __init__(self, collections: list[CollectionStored] | None = None) -> None:
        self._collections = list(collections) if collections is not None else []

    async def list_active(self) -> list[CollectionStored]:
        return sorted(self._collections, key=lambda c: (c.ordering, c.name))


class DbCollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[CollectionStored]:
        from src.models import Collection

        result = await self._session.execute(
            select(Collection)
            .where(Collection.is_active.is_(True))
            .order_by(Collection.ordering, Collection.title)
        )
        return [_to_domain(row) for row in result.scalars()]
