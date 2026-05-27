from __future__ import annotations

import asyncio
from uuid import UUID

from src.api.dependencies import get_current_user_id
from src.api.orders.dependencies import get_checkout_catalog_client
from src.main import app
from src.orders.db_models import Order as OrderRow
from src.orders.db_models import OrderStatus as DbOrderStatus
from src.orders.repository import UpstreamServiceError
from tests.order_test_utils import (
    OTHER_USER_ID,
    TEST_USER_ID,
    LiveCheckoutCatalogClient,
    auth_header,
    checkout_request_body,
    seed_cart_items,
)

SKU_ID_1 = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")


def _set_current_user(user_id: UUID) -> None:
    app.dependency_overrides[get_current_user_id] = lambda: user_id


def _create_order(client, *, user_id: UUID, idempotency_key: str) -> dict:
    seed_cart_items(user_id, [(SKU_ID_1, 1)])
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    response = client.post(
        "/api/v1/orders",
        headers={**auth_header(user_id), "Idempotency-Key": idempotency_key},
        json=checkout_request_body(user_id=user_id),
    )
    assert response.status_code == 201
    return response.json()


async def _set_order_status(order_id: UUID, status: DbOrderStatus) -> None:
    import src.orders.db as db_module

    async with db_module.SessionLocal() as session:
        order = await session.get(OrderRow, order_id)
        assert order is not None
        order.status = status
        await session.commit()


class FailingUnreserveClient(LiveCheckoutCatalogClient):
    async def unreserve(self, *, order_id, items):
        raise UpstreamServiceError("B2B temporarily unavailable", None)


def test_cancel_paid_order_transitions_to_cancelled(client) -> None:
    order = _create_order(
        client,
        user_id=TEST_USER_ID,
        idempotency_key="f47ac10b-58cc-4372-a567-0e02b2c3d479",
    )

    _set_current_user(TEST_USER_ID)
    response = client.post(f"/api/v1/orders/{order['id']}/cancel")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == order["id"]
    assert payload["status"] == "CANCELLED"


def test_unreserve_failure_transitions_to_cancel_pending(client) -> None:
    app.dependency_overrides[get_checkout_catalog_client] = lambda: FailingUnreserveClient()
    order = _create_order(
        client,
        user_id=TEST_USER_ID,
        idempotency_key="f47ac10b-58cc-4372-a567-0e02b2c3d47a",
    )

    _set_current_user(TEST_USER_ID)
    response = client.post(f"/api/v1/orders/{order['id']}/cancel")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "CANCEL_PENDING"


def test_cancel_assembling_order_returns_409(client) -> None:
    order = _create_order(
        client,
        user_id=TEST_USER_ID,
        idempotency_key="f47ac10b-58cc-4372-a567-0e02b2c3d47b",
    )
    asyncio.run(_set_order_status(UUID(order["id"]), DbOrderStatus.ASSEMBLING))

    _set_current_user(TEST_USER_ID)
    response = client.post(f"/api/v1/orders/{order['id']}/cancel")

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "CANCEL_NOT_ALLOWED"
    assert payload["current_status"] == "ASSEMBLING"


def test_other_user_order_returns_404(client) -> None:
    other_order = _create_order(
        client,
        user_id=OTHER_USER_ID,
        idempotency_key="f47ac10b-58cc-4372-a567-0e02b2c3d47c",
    )

    _set_current_user(TEST_USER_ID)
    response = client.post(f"/api/v1/orders/{other_order['id']}/cancel")

    assert response.status_code == 404
    assert response.json()["code"] == "ORDER_NOT_FOUND"
