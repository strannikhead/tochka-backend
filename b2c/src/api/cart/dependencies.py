from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.cart.b2b_client import B2BCartClient, HttpB2BCartClient, InMemoryB2BCartClient
from src.cart.repository import CartRepository, DbCartRepository
from src.database import get_session


async def get_cart_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CartRepository:
    return DbCartRepository(session)


def get_b2b_cart_client() -> B2BCartClient:
    if os.getenv("B2B_BASE_URL"):
        return HttpB2BCartClient()
    return InMemoryB2BCartClient()
