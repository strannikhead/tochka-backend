from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.orders.db import get_session
from src.orders.repository import HttpCheckoutCatalogClient, SqlAlchemyOrdersRepository
from src.orders.service import CheckoutService


def get_orders_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyOrdersRepository:
    return SqlAlchemyOrdersRepository(session)


def get_checkout_catalog_client() -> HttpCheckoutCatalogClient:
    return HttpCheckoutCatalogClient()


def get_checkout_service(
    repository: Annotated[SqlAlchemyOrdersRepository, Depends(get_orders_repository)],
    catalog_client: Annotated[HttpCheckoutCatalogClient, Depends(get_checkout_catalog_client)],
) -> CheckoutService:
    return CheckoutService(repository, catalog_client)
