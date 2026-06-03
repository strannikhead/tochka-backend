"""Tests for US-B2B-02: POST /api/v1/skus

Uses a real PostgreSQL database. Make sure the DB is up before running:
    docker compose -f docker-compose.db.yml up -d
    alembic upgrade head

Test DB: postgresql+psycopg://neomarket:neomarket_dev_2026@127.0.0.1:5433/neomarket_b2b
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
        cat = Category(
            name="Test Category",
            level=0,
            path="/test",
            is_active=True,
        )
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


async def _get_product_status(product_id: uuid.UUID) -> ProductStatus:
    async with _SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        return product.status


async def _add_existing_sku(product_id: uuid.UUID) -> None:
    async with _SessionLocal() as session:
        sku = SKU(
            product_id=product_id,
            name="Existing SKU",
            price=10000,
            images=[{"url": "https://example.com/img.jpg", "ordering": 0}],
            characteristics=[],
        )
        session.add(sku)
        await session.commit()


async def _cleanup(*ids: uuid.UUID) -> None:
    async with _SessionLocal() as session:
        for pid in ids:
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


def _valid_body(product_id: uuid.UUID) -> dict:
    return {
        "product_id": str(product_id),
        "name": "Red / L",
        "price": 5000,
        "discount": 0,
        "images": [{"url": "https://example.com/red-l.jpg", "ordering": 0}],
        "characteristics": [{"name": "Цвет", "value": "Красный"}],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_first_sku_transitions_product_to_on_moderation(
    client: TestClient, category_id: uuid.UUID
) -> None:
    product_id = asyncio.run(_make_product(ProductStatus.CREATED, category_id))
    try:
        with patch.object(ModerationClient, "send_created_event", new_callable=AsyncMock):
            response = client.post("/api/v1/skus", json=_valid_body(product_id))

        assert response.status_code == 201
        status_after = asyncio.run(_get_product_status(product_id))
        assert status_after == ProductStatus.ON_MODERATION
    finally:
        asyncio.run(_cleanup(product_id))


def test_first_sku_emits_created_event_to_moderation(
    client: TestClient, category_id: uuid.UUID
) -> None:
    product_id = asyncio.run(_make_product(ProductStatus.CREATED, category_id))
    try:
        with patch.object(
            ModerationClient, "send_created_event", new_callable=AsyncMock
        ) as mock_send:
            response = client.post("/api/v1/skus", json=_valid_body(product_id))

        assert response.status_code == 201
        mock_send.assert_awaited_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["product_id"] == product_id
        assert call_kwargs["seller_id"] == SELLER_ID
    finally:
        asyncio.run(_cleanup(product_id))


def test_second_sku_no_status_change(client: TestClient, category_id: uuid.UUID) -> None:
    product_id = asyncio.run(_make_product(ProductStatus.CREATED, category_id))
    asyncio.run(_add_existing_sku(product_id))
    # After the first SKU is added manually the product is still CREATED in DB
    # (we bypassed the service), so second call via API should not change status.
    try:
        with patch.object(
            ModerationClient, "send_created_event", new_callable=AsyncMock
        ) as mock_send:
            response = client.post("/api/v1/skus", json=_valid_body(product_id))

        assert response.status_code == 201
        # Product already had a SKU, so no status transition and no event.
        status_after = asyncio.run(_get_product_status(product_id))
        assert status_after == ProductStatus.CREATED
        mock_send.assert_not_awaited()
    finally:
        asyncio.run(_cleanup(product_id))


def test_add_sku_to_hard_blocked_product_returns_403(
    client: TestClient, category_id: uuid.UUID
) -> None:
    product_id = asyncio.run(_make_product(ProductStatus.HARD_BLOCKED, category_id))
    try:
        response = client.post("/api/v1/skus", json=_valid_body(product_id))

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"
    finally:
        asyncio.run(_cleanup(product_id))


def test_empty_images_is_allowed(client: TestClient, category_id: uuid.UUID) -> None:
    product_id = asyncio.run(_make_product(ProductStatus.CREATED, category_id))
    try:
        body = _valid_body(product_id)
        body["images"] = []

        with patch.object(ModerationClient, "send_created_event", new_callable=AsyncMock):
            response = client.post("/api/v1/skus", json=body)

        assert response.status_code == 201
        assert response.json()["images"] == []
    finally:
        asyncio.run(_cleanup(product_id))


def test_add_sku_to_another_sellers_product_returns_403(
    client: TestClient, category_id: uuid.UUID
) -> None:
    product_id = asyncio.run(
        _make_product(ProductStatus.CREATED, category_id, seller_id=OTHER_SELLER_ID)
    )
    try:
        response = client.post("/api/v1/skus", json=_valid_body(product_id))

        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"
    finally:
        asyncio.run(_cleanup(product_id))
