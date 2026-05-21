from __future__ import annotations

from typing import Annotated

from b2b.src.db import get_session
from b2b.src.products.application.service import ProductsService
from b2b.src.products.domain.repository import ProductsRepository
from b2b.src.products.infrastructure.sqlalchemy_repository import SqlAlchemyProductsRepository
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession


def get_products_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProductsRepository:
    return SqlAlchemyProductsRepository(session)


def get_products_service(
    repository: Annotated[ProductsRepository, Depends(get_products_repository)],
) -> ProductsService:
    return ProductsService(repository)
