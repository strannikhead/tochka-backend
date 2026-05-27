from uuid import UUID

from src.api.dependencies import get_current_user_id
from src.api.orders.dependencies import get_checkout_catalog_client
from src.main import app
from src.orders.repository import HttpCheckoutCatalogClient
from tests.order_test_utils import (
    CHECKOUT_USER_ID,
    auth_header,
    checkout_request_body,
    seed_cart_items,
)


def test_b2b_unavailable_returns_503(client):
    app.dependency_overrides[get_checkout_catalog_client] = lambda: HttpCheckoutCatalogClient(
        base_url="http://127.0.0.1:1"
    )

    sku_id = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")
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

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "B2B_UNAVAILABLE"
