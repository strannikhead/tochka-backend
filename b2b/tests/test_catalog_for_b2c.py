"""Tests for US-B2B-07: GET /api/v1/public/products and POST /api/v1/public/products/batch

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

from b2b.src.main import app
from b2b.src.models import SKU, Category, Product, ProductStatus

TEST_DB_URL = "postgresql+psycopg://neomarket:neomarket_dev_2026@127.0.0.1:5433/neomarket_b2b"

_engine = create_async_engine(TEST_DB_URL, echo=False)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)

SERVICE_HEADERS = {"X-Service-Key": "dev-service-key"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_category() -> uuid.UUID:
    async with _SessionLocal() as session:
        cat = Category(name="B2C Test Category", level=0, path="/b2c-test", is_active=True)
        session.add(cat)
        await session.commit()
        return cat.id


async def _make_product(
    category_id: uuid.UUID,
    *,
    status: ProductStatus = ProductStatus.MODERATED,
    deleted: bool = False,
) -> uuid.UUID:
    async with _SessionLocal() as session:
        product = Product(
            seller_id=uuid.uuid4(),
            title="B2C Test Product",
            category_id=category_id,
            status=status,
            deleted=deleted,
            images=[{"url": "/s3/test.jpg"}],
            characteristics=[],
        )
        session.add(product)
        await session.commit()
        return product.id


async def _make_sku(
    product_id: uuid.UUID,
    *,
    active_quantity: int = 10,
    cost_price: int = 5000,
) -> uuid.UUID:
    async with _SessionLocal() as session:
        sku = SKU(
            product_id=product_id,
            name="Test SKU",
            price=10000,
            cost_price=cost_price,
            stock_quantity=active_quantity,
            active_quantity=active_quantity,
            reserved_quantity=2,
            images=[],
            characteristics=[],
        )
        session.add(sku)
        await session.commit()
        return sku.id


async def _cleanup(*product_ids: uuid.UUID) -> None:
    async with _SessionLocal() as session:
        for pid in product_ids:
            p = await session.get(Product, pid)
            if p:
                await session.delete(p)
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_catalog_returns_moderated_in_stock_products(
    client: TestClient, category_id: uuid.UUID
) -> None:
    visible_id = asyncio.run(_make_product(category_id, status=ProductStatus.MODERATED))
    created_id = asyncio.run(_make_product(category_id, status=ProductStatus.CREATED))
    deleted_id = asyncio.run(
        _make_product(category_id, status=ProductStatus.MODERATED, deleted=True)
    )
    no_stock_id = asyncio.run(_make_product(category_id, status=ProductStatus.MODERATED))

    asyncio.run(_make_sku(visible_id, active_quantity=5))
    asyncio.run(_make_sku(created_id, active_quantity=5))
    asyncio.run(_make_sku(deleted_id, active_quantity=5))
    asyncio.run(_make_sku(no_stock_id, active_quantity=0))

    try:
        resp = client.get(
            "/api/v1/public/products",
            params={"category_id": str(category_id), "limit": 100},
            headers=SERVICE_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        ids = {item["id"] for item in data["items"]}
        assert str(visible_id) in ids
        assert str(created_id) not in ids
        assert str(deleted_id) not in ids
        assert str(no_stock_id) not in ids
    finally:
        asyncio.run(_cleanup(visible_id, created_id, deleted_id, no_stock_id))


def test_catalog_excludes_hard_blocked(
    client: TestClient, category_id: uuid.UUID
) -> None:
    hard_blocked_id = asyncio.run(
        _make_product(category_id, status=ProductStatus.HARD_BLOCKED)
    )
    asyncio.run(_make_sku(hard_blocked_id, active_quantity=5))

    try:
        resp = client.get(
            "/api/v1/public/products",
            params={"category_id": str(category_id), "limit": 100},
            headers=SERVICE_HEADERS,
        )
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["items"]}
        assert str(hard_blocked_id) not in ids
    finally:
        asyncio.run(_cleanup(hard_blocked_id))


def test_catalog_missing_service_key_returns_401(client: TestClient) -> None:
    resp = client.get("/api/v1/public/products")
    assert resp.status_code == 401
    body = resp.json()
    assert body.get("code") == "UNAUTHORIZED"


def test_catalog_response_has_no_cost_price(
    client: TestClient, category_id: uuid.UUID
) -> None:
    product_id = asyncio.run(_make_product(category_id))
    asyncio.run(_make_sku(product_id, active_quantity=5, cost_price=9999))

    try:
        resp = client.post(
            "/api/v1/public/products/batch",
            json={"product_ids": [str(product_id)]},
            headers=SERVICE_HEADERS,
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        for sku in items[0]["skus"]:
            assert "cost_price" not in sku
            assert "reserved_quantity" not in sku
    finally:
        asyncio.run(_cleanup(product_id))


def test_batch_ids_returns_visible_subset(
    client: TestClient, category_id: uuid.UUID
) -> None:
    visible_id = asyncio.run(_make_product(category_id, status=ProductStatus.MODERATED))
    asyncio.run(_make_sku(visible_id, active_quantity=3))

    blocked_id = asyncio.run(_make_product(category_id, status=ProductStatus.BLOCKED))
    asyncio.run(_make_sku(blocked_id, active_quantity=3))

    nonexistent_id = uuid.uuid4()

    try:
        resp = client.post(
            "/api/v1/public/products/batch",
            json={"product_ids": [str(visible_id), str(blocked_id), str(nonexistent_id)]},
            headers=SERVICE_HEADERS,
        )
        assert resp.status_code == 200
        items = resp.json()
        returned_ids = {item["id"] for item in items}
        assert str(visible_id) in returned_ids
        assert str(blocked_id) not in returned_ids
        assert str(nonexistent_id) not in returned_ids
    finally:
        asyncio.run(_cleanup(visible_id, blocked_id))
