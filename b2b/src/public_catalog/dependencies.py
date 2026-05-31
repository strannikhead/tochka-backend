from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from b2b.src.db import get_session
from b2b.src.public_catalog.application.service import PublicCatalogService


async def get_public_catalog_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PublicCatalogService:
    return PublicCatalogService(session)
