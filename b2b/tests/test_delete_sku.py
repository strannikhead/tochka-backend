"""Tests for US-B2B-12: DELETE /api/v1/skus/{sku_id}

Uses a real PostgreSQL database. Make sure the DB is up before running:
    docker compose -f docker-compose.db.yml up -d
    alembic upgrade head

Test DB: postgresql+psycopg://neomarket:neomarket_dev_2026@127.0.0.1:5432/neomarket_b2b
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from b2b.src.auth import get_current_seller_id
from b2b.src.b2c_client import B2cClient
from b2b.src.main import app
from b2b.src.models import SKU, Category, Product, ProductStatus
from b2b.src.skus.infrastructure.moderation_client import ModerationClient

TEST_DB_URL = "postgresql+psycopg://neomarket:neomarket_dev_2026@127.0.0.1:5432/neomarket_b2b"

_engine = create_async_engine(TEST_DB_URL, echo=False)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)

SELLER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
OTHER_SELLER_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440000")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_category() -> uuid.UUID:
    async with _SessionLocal() as session:
        cat = Category(name="Test Category", level=0, path="/test", is_active=True)
        session.add(cat)
        await session.commit()
        return cat.id


async def _make_product(
    status: ProductStatus,
    category_id: uuid.UUID,
    seller_id: uuid.UUID = SELLER_ID,
) -> uuid.UUID:
    async with _SessionLocal() as session:
        product = Product(
            seller_id=seller_id,
            title="Test Product",
            category_id=category_id,
            status=status,
            images=[],
            characteristics=[],
        )
        session.add(product)
        await session.commit()
        return product.id


async def _make_sku(
    product_id: uuid.UUID,
    *,
    reserved_quantity: int = 0,
    active_quantity: int = 0,
) -> uuid.UUID:
    async with _SessionLocal() as session:
        sku = SKU(
            product_id=product_id,
            name="Test SKU",
            price=10000,
            images=[],
            characteristics=[],
            reserved_quantity=reserved_quantity,
            active_quantity=active_quantity,
        )
        session.add(sku)
        await session.commit()
        return sku.id


async def _get_product_status(product_id: uuid.UUID) -> ProductStatus:
    async with _SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        return product.status


async def _sku_exists(sku_id: uuid.UUID) -> bool:
    async with _SessionLocal() as session:
        sku = await session.get(SKU, sku_id)
        return sku is not None


async def _cleanup(*product_ids: uuid.UUID) -> None:
    async with _SessionLocal() as session:
        for pid in product_ids:
            product = await session.get(Product, pid)
            if product:
                await session.delete(product)
        await session.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def category_id() -> uuid.UUID:
    return asyncio.run(_make_category())


@pytest.fixture()
def client() -> Generator[TestClient]:
    app.dependency_overrides[get_current_seller_id] = lambda: SELLER_ID
    with TestClient(app) as c:
        yield c
    app.dependency_overrides = {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_delete_sku_succeeds(client: TestClient, category_id: uuid.UUID) -> None:
    product_id = asyncio.run(_make_product(ProductStatus.CREATED, category_id))
    sku_to_delete = asyncio.run(_make_sku(product_id))
    sku_to_keep = asyncio.run(_make_sku(product_id))
    try:
        response = client.delete(f"/api/v1/skus/{sku_to_delete}")

        assert response.status_code == 204
        assert not asyncio.run(_sku_exists(sku_to_delete))
        assert asyncio.run(_sku_exists(sku_to_keep))
        assert asyncio.run(_get_product_status(product_id)) == ProductStatus.CREATED
    finally:
        asyncio.run(_cleanup(product_id))


def test_delete_sku_with_active_reserves_returns_409(
    client: TestClient, category_id: uuid.UUID
) -> None:
    product_id = asyncio.run(_make_product(ProductStatus.CREATED, category_id))
    sku_id = asyncio.run(_make_sku(product_id, reserved_quantity=3))
    try:
        response = client.delete(f"/api/v1/skus/{sku_id}")

        assert response.status_code == 409
        assert response.json()["code"] == "CONFLICT"
        assert asyncio.run(_sku_exists(sku_id))
    finally:
        asyncio.run(_cleanup(product_id))


def test_last_sku_on_moderation_transitions_product_to_created(
    client: TestClient, category_id: uuid.UUID
) -> None:
    product_id = asyncio.run(_make_product(ProductStatus.ON_MODERATION, category_id))
    sku_id = asyncio.run(_make_sku(product_id))
    try:
        with patch.object(
            ModerationClient, "send_deleted_event", new_callable=AsyncMock
        ) as mock_deleted:
            response = client.delete(f"/api/v1/skus/{sku_id}")

        assert response.status_code == 204
        assert asyncio.run(_get_product_status(product_id)) == ProductStatus.CREATED
        mock_deleted.assert_awaited_once()
        call_kwargs = mock_deleted.call_args.kwargs
        assert call_kwargs["product_id"] == product_id
        assert call_kwargs["seller_id"] == SELLER_ID
    finally:
        asyncio.run(_cleanup(product_id))


def test_delete_sku_hard_blocked_product_returns_403(
    client: TestClient, category_id: uuid.UUID
) -> None:
    product_id = asyncio.run(_make_product(ProductStatus.HARD_BLOCKED, category_id))
    sku_id = asyncio.run(_make_sku(product_id))
    try:
        response = client.delete(f"/api/v1/skus/{sku_id}")

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"
        assert asyncio.run(_sku_exists(sku_id))
    finally:
        asyncio.run(_cleanup(product_id))


def test_sku_out_of_stock_event_on_moderated_product(
    client: TestClient, category_id: uuid.UUID
) -> None:
    product_id = asyncio.run(_make_product(ProductStatus.MODERATED, category_id))
    sku_to_delete = asyncio.run(_make_sku(product_id, active_quantity=5))
    _sku_to_keep = asyncio.run(_make_sku(product_id))
    try:
        with patch.object(
            B2cClient, "send_sku_out_of_stock", new_callable=AsyncMock
        ) as mock_b2c:
            response = client.delete(f"/api/v1/skus/{sku_to_delete}")

        assert response.status_code == 204
        mock_b2c.assert_awaited_once()
        call_kwargs = mock_b2c.call_args.kwargs
        assert call_kwargs["sku_id"] == sku_to_delete
        assert call_kwargs["product_id"] == product_id
        assert call_kwargs["available_quantity"] == 0
    finally:
        asyncio.run(_cleanup(product_id))


def test_hard_blocked_checked_before_reserves(
    client: TestClient, category_id: uuid.UUID
) -> None:
    """Guardrail order: HARD_BLOCKED must be checked before reserved_quantity."""
    product_id = asyncio.run(_make_product(ProductStatus.HARD_BLOCKED, category_id))
    sku_id = asyncio.run(_make_sku(product_id, reserved_quantity=5))
    try:
        response = client.delete(f"/api/v1/skus/{sku_id}")

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"
    finally:
        asyncio.run(_cleanup(product_id))
