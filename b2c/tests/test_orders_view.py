from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from src.api.dependencies import get_current_user_id
from src.main import app
from tests.order_test_utils import auth_header

TEST_USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_USER_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SKU_ID_1 = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")
SKU_ID_2 = UUID("8a4e3f9c-1a2b-4c8d-9e5f-6b7a8c9d0e1f")


@pytest.fixture(autouse=True)
def clear_overrides() -> None:
    yield
    app.dependency_overrides = {}


def _create_order(client: TestClient, *, user_id: UUID, idempotency_key: str, sku_id: UUID) -> dict:
    response = client.post(
        "/api/v1/orders",
        headers=auth_header(user_id),
        json={
            "idempotency_key": idempotency_key,
            "items": [{"sku_id": str(sku_id), "quantity": 1}],
            "delivery_address": "г. Екатеринбург, ул. Мира 19, кв. 42",
        },
    )
    assert response.status_code == 201
    return response.json()


async def _update_b2b_sku_price(sku_id: UUID, price: int) -> None:
    from b2b.src import db as b2b_db_module
    from b2b.src.models import SKU as B2BSKU

    async with b2b_db_module.SessionLocal() as session:
        sku = await session.get(B2BSKU, sku_id)
        assert sku is not None
        sku.price = price
        await session.commit()


def _set_current_user(user_id: UUID) -> None:
    app.dependency_overrides[get_current_user_id] = lambda: user_id


def test_orders_list_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/orders")

    assert response.status_code == 401
    assert response.json() == {"code": "UNAUTHORIZED", "message": "Требуется авторизация"}


def test_orders_list_returns_own_orders_paginated(client: TestClient) -> None:
    first_order = _create_order(
        client,
        user_id=TEST_USER_ID,
        idempotency_key="f47ac10b-58cc-4372-a567-0e02b2c3d479",
        sku_id=SKU_ID_1,
    )
    _create_order(
        client,
        user_id=TEST_USER_ID,
        idempotency_key="f47ac10b-58cc-4372-a567-0e02b2c3d47a",
        sku_id=SKU_ID_2,
    )
    _create_order(
        client,
        user_id=OTHER_USER_ID,
        idempotency_key="f47ac10b-58cc-4372-a567-0e02b2c3d47b",
        sku_id=SKU_ID_1,
    )

    _set_current_user(TEST_USER_ID)
    response = client.get("/api/v1/orders?limit=1&offset=1&status=PAID")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 2
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == first_order["id"]
    assert payload["items"][0]["items_count"] == 1


def test_order_detail_shows_fixed_prices(client: TestClient) -> None:
    order = _create_order(
        client,
        user_id=TEST_USER_ID,
        idempotency_key="f47ac10b-58cc-4372-a567-0e02b2c3d47c",
        sku_id=SKU_ID_1,
    )
    asyncio.run(_update_b2b_sku_price(SKU_ID_1, 99999999))

    _set_current_user(TEST_USER_ID)
    response = client.get(f"/api/v1/orders/{order['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == order["id"]
    assert payload["status"] == "PAID"
    assert payload["total_amount"] == 12999000
    assert payload["items"][0]["unit_price"] == 12999000
    assert payload["items"][0]["line_total"] == 12999000


def test_other_user_order_returns_404_not_403(client: TestClient) -> None:
    other_order = _create_order(
        client,
        user_id=OTHER_USER_ID,
        idempotency_key="f47ac10b-58cc-4372-a567-0e02b2c3d47d",
        sku_id=SKU_ID_1,
    )

    _set_current_user(TEST_USER_ID)
    response = client.get(f"/api/v1/orders/{other_order['id']}")

    assert response.status_code == 404
    assert response.json()["code"] == "ORDER_NOT_FOUND"
