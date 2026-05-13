from __future__ import annotations

from src.cart.b2b_client import B2BCartClient, InMemoryB2BCartClient
from src.cart.repository import CartRepository, InMemoryCartRepository


def get_cart_repository() -> CartRepository:
    return InMemoryCartRepository()


def get_b2b_cart_client() -> B2BCartClient:
    return InMemoryB2BCartClient()
