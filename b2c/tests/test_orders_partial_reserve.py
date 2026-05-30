from dataclasses import replace
from uuid import UUID

from src.api.dependencies import get_current_user_id
from src.api.orders.dependencies import get_checkout_catalog_client
from src.main import app
from src.orders.domain import ReserveFailedItem, ReserveResult
from tests.order_test_utils import (
    CHECKOUT_USER_ID,
    LiveCheckoutCatalogClient,
    auth_header,
    checkout_request_body,
    seed_cart_items,
)


class FailingReserveClient(LiveCheckoutCatalogClient):
    async def reserve(self, *, order_id, idempotency_key, items):
        failed_items = tuple(
            ReserveFailedItem(
                sku_id=item.sku_id,
                requested=item.quantity,
                available=item.quantity,
                reason="INSUFFICIENT_STOCK",
            )
            for item in items
        )
        return ReserveResult(reserved=False, failed_items=failed_items)


class NonModeratedCatalogClient(LiveCheckoutCatalogClient):
    async def get_skus_by_ids(self, sku_ids):
        skus = await super().get_skus_by_ids(sku_ids)
        target_sku_id = sku_ids[0]
        return [
            replace(sku, product_status="CREATED") if sku.sku_id == target_sku_id else sku
            for sku in skus
        ]

    async def reserve(self, *, order_id, idempotency_key, items):
        raise AssertionError("reserve must not be called for non-moderated products")


def test_partial_reserve_failure_returns_409(client):
    sku_id = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")
    failing_sku_id = UUID("8a4e3f9c-1a2b-4c8d-9e5f-6b7a8c9d0e1f")

    app.dependency_overrides[get_checkout_catalog_client] = lambda: FailingReserveClient()
    seed_cart_items(CHECKOUT_USER_ID, [(sku_id, 1), (failing_sku_id, 1)])
    app.dependency_overrides[get_current_user_id] = lambda: CHECKOUT_USER_ID

    response = client.post(
        "/api/v1/orders",
        headers={
            **auth_header(CHECKOUT_USER_ID),
            "Idempotency-Key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        },
        json=checkout_request_body(user_id=CHECKOUT_USER_ID),
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "RESERVE_FAILED"
    assert any(item["sku_id"] == str(failing_sku_id) for item in payload["failed_items"])


def test_non_moderated_product_is_rejected_before_reserve(client):
    sku_id = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")

    app.dependency_overrides[get_checkout_catalog_client] = lambda: NonModeratedCatalogClient()
    seed_cart_items(CHECKOUT_USER_ID, [(sku_id, 1)])
    app.dependency_overrides[get_current_user_id] = lambda: CHECKOUT_USER_ID

    response = client.post(
        "/api/v1/orders",
        headers={
            **auth_header(CHECKOUT_USER_ID),
            "Idempotency-Key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        },
        json=checkout_request_body(user_id=CHECKOUT_USER_ID),
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["is_valid"] is False
    assert payload["issues"][0]["type"] == "PRODUCT_BLOCKED"
