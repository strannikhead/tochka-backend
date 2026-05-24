from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.banners.repository import BannerRepository, DbBannerRepository
from src.database import get_session

from b2c.src.catalog.repository import CatalogRepository, HttpCatalogRepository


def get_catalog_repository() -> CatalogRepository:
    return HttpCatalogRepository()


async def get_banner_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BannerRepository:
    return DbBannerRepository(session)
