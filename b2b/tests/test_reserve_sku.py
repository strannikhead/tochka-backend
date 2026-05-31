"""Tests for US-B2B-08: POST /api/v1/inventory/reserve and /unreserve

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

from b2b.src.inventory.b2c_client import B2cClient
from b2b.src.inventory.models import InventoryReservation
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
        cat = Category(name="Test Category", level=0, path="/test", is_active=True)
        session.add(cat)
        await session.commit()
        return cat.id


async def _make_product(category_id: uuid.UUID) -> uuid.UUID:
    async with _SessionLocal() as session:
        product = Product(
            seller_id=SELLER_ID,
            title="Test Product",
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
    active_quantity: int = 10,
    reserved_quantity: int = 0,
) -> uuid.UUID:
    async with _SessionLocal() as session:
        sku = SKU(
            product_id=product_id,
            name="Test SKU",
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


async def _cleanup_reservation(order_id: uuid.UUID) -> None:
    from sqlalchemy import select

    async with _SessionLocal() as session:
        result = await session.execute(
            select(InventoryReservation).where(InventoryReservation.order_id == order_id)
        )
        reservation = result.scalar_one_or_none()
        if reservation:
            await session.delete(reservation)
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


def _reserve_body(
    order_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    items: list[dict],
) -> dict:
    return {
        "order_id": str(order_id),
        "idempotency_key": str(idempotency_key),
        "items": items,
    }


def _unreserve_body(order_id: uuid.UUID, items: list[dict]) -> dict:
    return {"order_id": str(order_id), "items": items}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_reserve_all_skus_succeeds(client: TestClient, category_id: uuid.UUID) -> None:
    product_id = asyncio.run(_make_product(category_id))
    sku_id = asyncio.run(_make_sku(product_id, active_quantity=5))
    order_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    try:
        items = [{"sku_id": str(sku_id), "quantity": 3}]
        with patch.object(B2cClient, "send_sku_out_of_stock", new_callable=AsyncMock):
            response = client.post(
                "/api/v1/inventory/reserve",
                json=_reserve_body(order_id, idempotency_key, items),
                headers=SERVICE_HEADERS,
            )

        assert response.status_code == 200
        assert response.json()["status"] == "RESERVED"

        sku = asyncio.run(_get_sku(sku_id))
        assert sku.active_quantity == 2
        assert sku.reserved_quantity == 3
    finally:
        asyncio.run(_cleanup_reservation(order_id))
        asyncio.run(_cleanup_product(product_id))


def test_partial_insufficient_stock_returns_409_all_rollback(
    client: TestClient, category_id: uuid.UUID
) -> None:
    product_id = asyncio.run(_make_product(category_id))
    sku_id_ok = asyncio.run(_make_sku(product_id, active_quantity=10))
    sku_id_short = asyncio.run(_make_sku(product_id, active_quantity=1))
    order_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    try:
        response = client.post(
            "/api/v1/inventory/reserve",
            json=_reserve_body(
                order_id,
                idempotency_key,
                [
                    {"sku_id": str(sku_id_ok), "quantity": 5},
                    {"sku_id": str(sku_id_short), "quantity": 5},
                ],
            ),
            headers=SERVICE_HEADERS,
        )

        assert response.status_code == 409

        # Neither SKU must have been touched — all-or-nothing rollback.
        sku_ok = asyncio.run(_get_sku(sku_id_ok))
        sku_short = asyncio.run(_get_sku(sku_id_short))
        assert sku_ok.active_quantity == 10
        assert sku_ok.reserved_quantity == 0
        assert sku_short.active_quantity == 1
        assert sku_short.reserved_quantity == 0
    finally:
        asyncio.run(_cleanup_product(product_id))


def test_idempotent_reserve_returns_200_without_double_deduction(
    client: TestClient, category_id: uuid.UUID
) -> None:
    product_id = asyncio.run(_make_product(category_id))
    sku_id = asyncio.run(_make_sku(product_id, active_quantity=10))
    order_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    body = _reserve_body(order_id, idempotency_key, [{"sku_id": str(sku_id), "quantity": 3}])
    try:
        with patch.object(B2cClient, "send_sku_out_of_stock", new_callable=AsyncMock):
            r1 = client.post("/api/v1/inventory/reserve", json=body, headers=SERVICE_HEADERS)
            r2 = client.post("/api/v1/inventory/reserve", json=body, headers=SERVICE_HEADERS)

        assert r1.status_code == 200
        assert r2.status_code == 200

        sku = asyncio.run(_get_sku(sku_id))
        # Quantity must have been deducted only once.
        assert sku.active_quantity == 7
        assert sku.reserved_quantity == 3
    finally:
        asyncio.run(_cleanup_reservation(order_id))
        asyncio.run(_cleanup_product(product_id))


def test_sku_out_of_stock_event_emitted(client: TestClient, category_id: uuid.UUID) -> None:
    product_id = asyncio.run(_make_product(category_id))
    sku_id = asyncio.run(_make_sku(product_id, active_quantity=2))
    order_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    try:
        items = [{"sku_id": str(sku_id), "quantity": 2}]
        with patch.object(B2cClient, "send_sku_out_of_stock", new_callable=AsyncMock) as mock_send:
            response = client.post(
                "/api/v1/inventory/reserve",
                json=_reserve_body(order_id, idempotency_key, items),
                headers=SERVICE_HEADERS,
            )

        assert response.status_code == 200

        mock_send.assert_awaited_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["sku_id"] == sku_id
        assert call_kwargs["product_id"] == product_id
        assert call_kwargs["available_quantity"] == 0
    finally:
        asyncio.run(_cleanup_reservation(order_id))
        asyncio.run(_cleanup_product(product_id))


def test_unreserve_restores_quantities(client: TestClient, category_id: uuid.UUID) -> None:
    product_id = asyncio.run(_make_product(category_id))
    sku_id = asyncio.run(_make_sku(product_id, active_quantity=10))
    order_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()
    try:
        items = [{"sku_id": str(sku_id), "quantity": 4}]
        with patch.object(B2cClient, "send_sku_out_of_stock", new_callable=AsyncMock):
            client.post(
                "/api/v1/inventory/reserve",
                json=_reserve_body(order_id, idempotency_key, items),
                headers=SERVICE_HEADERS,
            )

        sku_after_reserve = asyncio.run(_get_sku(sku_id))
        assert sku_after_reserve.active_quantity == 6
        assert sku_after_reserve.reserved_quantity == 4

        response = client.post(
            "/api/v1/inventory/unreserve",
            json=_unreserve_body(order_id, [{"sku_id": str(sku_id), "quantity": 4}]),
            headers=SERVICE_HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "UNRESERVED"

        sku_after_unreserve = asyncio.run(_get_sku(sku_id))
        assert sku_after_unreserve.active_quantity == 10
        assert sku_after_unreserve.reserved_quantity == 0
    finally:
        asyncio.run(_cleanup_product(product_id))
