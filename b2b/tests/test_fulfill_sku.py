"""Tests for US-B2B-10: POST /api/v1/inventory/fulfill

Uses a real PostgreSQL database. Make sure the DB is up before running:
    docker compose -f docker-compose.db.yml up -d
    alembic upgrade head

Test DB: postgresql+psycopg://neomarket:neomarket_dev_2026@127.0.0.1:5433/neomarket_b2b
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from b2b.src.inventory.models import FulfilledOrder
from b2b.src.main import app
from b2b.src.models import SKU, Category, Product, ProductStatus

TEST_DB_URL = "postgresql+psycopg://neomarket:neomarket_dev_2026@127.0.0.1:5433/neomarket_b2b"

_engine = create_async_engine(TEST_DB_URL, echo=False)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)

SELLER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
SERVICE_HEADERS = {"X-Service-Key": "dev-service-key"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_category() -> uuid.UUID:
    async with _SessionLocal() as session:
        cat = Category(name="Fulfill Test Category", level=0, path="/fulfill-test", is_active=True)
        session.add(cat)
        await session.commit()
        return cat.id


async def _make_product(category_id: uuid.UUID) -> uuid.UUID:
    async with _SessionLocal() as session:
        product = Product(
            seller_id=SELLER_ID,
            title="Fulfill Test Product",
            category_id=category_id,
            status=ProductStatus.MODERATED,
            images=[],
            characteristics=[],
        )
        session.add(product)
        await session.commit()
        return product.id


async def _make_sku(
    product_id: uuid.UUID,
    *,
    active_quantity: int = 0,
    reserved_quantity: int = 5,
) -> uuid.UUID:
    async with _SessionLocal() as session:
        sku = SKU(
            product_id=product_id,
            name="Fulfill Test SKU",
            price=10000,
            stock_quantity=active_quantity + reserved_quantity,
            active_quantity=active_quantity,
            reserved_quantity=reserved_quantity,
            images=[],
            characteristics=[],
        )
        session.add(sku)
        await session.commit()
        return sku.id


async def _get_sku(sku_id: uuid.UUID) -> SKU:
    async with _SessionLocal() as session:
        sku = await session.get(SKU, sku_id)
        assert sku is not None
        return sku


async def _cleanup_fulfilled(order_id: uuid.UUID) -> None:
    from sqlalchemy import select

    async with _SessionLocal() as session:
        result = await session.execute(
            select(FulfilledOrder).where(FulfilledOrder.order_id == order_id)
        )
        row = result.scalar_one_or_none()
        if row:
            await session.delete(row)
        await session.commit()


async def _cleanup_product(product_id: uuid.UUID) -> None:
    async with _SessionLocal() as session:
        product = await session.get(Product, product_id)
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
    with TestClient(app) as c:
        yield c


def _fulfill_body(order_id: uuid.UUID, items: list[dict]) -> dict:
    return {"order_id": str(order_id), "items": items}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_fulfill_decreases_reserved_quantity(client: TestClient, category_id: uuid.UUID) -> None:
    product_id = asyncio.run(_make_product(category_id))
    sku_id = asyncio.run(_make_sku(product_id, active_quantity=0, reserved_quantity=5))
    order_id = uuid.uuid4()
    try:
        response = client.post(
            "/api/v1/inventory/fulfill",
            json=_fulfill_body(order_id, [{"sku_id": str(sku_id), "quantity": 3}]),
            headers=SERVICE_HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "FULFILLED"
        assert response.json()["order_id"] == str(order_id)

        sku = asyncio.run(_get_sku(sku_id))
        assert sku.reserved_quantity == 2
        assert sku.stock_quantity == 2
    finally:
        asyncio.run(_cleanup_fulfilled(order_id))
        asyncio.run(_cleanup_product(product_id))


def test_active_quantity_unchanged(client: TestClient, category_id: uuid.UUID) -> None:
    product_id = asyncio.run(_make_product(category_id))
    sku_id = asyncio.run(_make_sku(product_id, active_quantity=7, reserved_quantity=5))
    order_id = uuid.uuid4()
    try:
        response = client.post(
            "/api/v1/inventory/fulfill",
            json=_fulfill_body(order_id, [{"sku_id": str(sku_id), "quantity": 5}]),
            headers=SERVICE_HEADERS,
        )

        assert response.status_code == 200

        sku = asyncio.run(_get_sku(sku_id))
        assert sku.active_quantity == 7
        assert sku.reserved_quantity == 0
        assert sku.stock_quantity == 7
    finally:
        asyncio.run(_cleanup_fulfilled(order_id))
        asyncio.run(_cleanup_product(product_id))


def test_idempotent_fulfill_no_double_deduction(client: TestClient, category_id: uuid.UUID) -> None:
    product_id = asyncio.run(_make_product(category_id))
    sku_id = asyncio.run(_make_sku(product_id, active_quantity=0, reserved_quantity=10))
    order_id = uuid.uuid4()
    body = _fulfill_body(order_id, [{"sku_id": str(sku_id), "quantity": 4}])
    try:
        r1 = client.post("/api/v1/inventory/fulfill", json=body, headers=SERVICE_HEADERS)
        r2 = client.post("/api/v1/inventory/fulfill", json=body, headers=SERVICE_HEADERS)

        assert r1.status_code == 200
        assert r2.status_code == 200

        sku = asyncio.run(_get_sku(sku_id))
        assert sku.reserved_quantity == 6
        assert sku.stock_quantity == 6
    finally:
        asyncio.run(_cleanup_fulfilled(order_id))
        asyncio.run(_cleanup_product(product_id))


def test_missing_service_key_returns_401(client: TestClient, category_id: uuid.UUID) -> None:
    order_id = uuid.uuid4()
    response = client.post(
        "/api/v1/inventory/fulfill",
        json=_fulfill_body(order_id, [{"sku_id": str(uuid.uuid4()), "quantity": 1}]),
    )
    assert response.status_code == 401


def test_overfulfill_returns_409_no_change(client: TestClient, category_id: uuid.UUID) -> None:
    product_id = asyncio.run(_make_product(category_id))
    sku_id = asyncio.run(_make_sku(product_id, active_quantity=0, reserved_quantity=2))
    order_id = uuid.uuid4()
    try:
        response = client.post(
            "/api/v1/inventory/fulfill",
            json=_fulfill_body(order_id, [{"sku_id": str(sku_id), "quantity": 5}]),
            headers=SERVICE_HEADERS,
        )

        assert response.status_code == 409

        sku = asyncio.run(_get_sku(sku_id))
        assert sku.reserved_quantity == 2
        assert sku.stock_quantity == 2
    finally:
        asyncio.run(_cleanup_product(product_id))


def test_missing_sku_returns_404(client: TestClient, category_id: uuid.UUID) -> None:
    order_id = uuid.uuid4()
    response = client.post(
        "/api/v1/inventory/fulfill",
        json=_fulfill_body(order_id, [{"sku_id": str(uuid.uuid4()), "quantity": 1}]),
        headers=SERVICE_HEADERS,
    )
    assert response.status_code == 404
