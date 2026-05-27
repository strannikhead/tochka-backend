from uuid import UUID

from src.api.dependencies import get_current_user_id
from src.main import app
from tests.order_test_utils import (
    CHECKOUT_USER_ID,
    auth_header,
    checkout_request_body,
    seed_cart_items,
)


def test_checkout_creates_paid_order_with_fixed_prices(client):
    sku_id = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")
    other_sku_id = UUID("8a4e3f9c-1a2b-4c8d-9e5f-6b7a8c9d0e1f")

    seed_cart_items(CHECKOUT_USER_ID, [(sku_id, 2), (other_sku_id, 1)])
    app.dependency_overrides[get_current_user_id] = lambda: CHECKOUT_USER_ID

    response = client.post(
        "/api/v1/orders",
        headers={
            **auth_header(CHECKOUT_USER_ID),
            "Idempotency-Key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        },
        json=checkout_request_body(user_id=CHECKOUT_USER_ID),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "PAID"
    assert payload["buyer_id"] == str(CHECKOUT_USER_ID)
    assert payload["subtotal"] == 38997000
    assert payload["total"] == 38997000
    assert payload["address"]["id"] == str(CHECKOUT_USER_ID)
    assert payload["items"][0]["unit_price"] == 12999000
    assert payload["items"][0]["name"] == "iPhone 15 Pro Max 256GB Black"
    assert payload["items"][1]["line_total"] == 12999000
