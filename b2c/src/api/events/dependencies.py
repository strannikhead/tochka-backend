from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.cart.repository import CartRepository, DbCartRepository
from src.database import get_session
from src.events.repository import DbEventIdempotencyRepository, EventIdempotencyRepository
from src.events.service import ProductEventService


def get_event_cart_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CartRepository:
    return DbCartRepository(session)


def get_event_idempotency_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventIdempotencyRepository:
    return DbEventIdempotencyRepository(session)


def get_product_event_service(
    cart_repository: Annotated[CartRepository, Depends(get_event_cart_repository)],
    idempotency_repository: Annotated[
        EventIdempotencyRepository, Depends(get_event_idempotency_repository)
    ],
) -> ProductEventService:
    return ProductEventService(cart_repository, idempotency_repository)
