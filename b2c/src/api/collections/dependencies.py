from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.collections.b2b_client import (
    CollectionsB2BClient,
    HttpCollectionsB2BClient,
    InMemoryCollectionsB2BClient,
)
from src.collections.repository import CollectionRepository, DbCollectionRepository
from src.database import get_session


async def get_collection_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionRepository:
    return DbCollectionRepository(session)


def get_collections_b2b_client() -> CollectionsB2BClient:
    if os.getenv("B2B_BASE_URL"):
        return HttpCollectionsB2BClient()
    return InMemoryCollectionsB2BClient()
