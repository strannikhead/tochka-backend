from uuid import UUID

from tests.order_test_utils import auth_header


def test_checkout_creates_paid_order_with_fixed_prices(client):
    sku_id = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")
    other_sku_id = UUID("8a4e3f9c-1a2b-4c8d-9e5f-6b7a8c9d0e1f")

    response = client.post(
        "/api/v1/orders",
        headers=auth_header(UUID("111e8400-e29b-41d4-a716-446655440000")),
        json={
            "idempotency_key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "items": [
                {"sku_id": str(sku_id), "quantity": 2},
                {"sku_id": str(other_sku_id), "quantity": 1},
            ],
            "delivery_address": "г. Екатеринбург, ул. Мира 19, кв. 42",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "PAID"
    assert payload["total_amount"] == 38997000
    assert payload["delivery_address"] == "г. Екатеринбург, ул. Мира 19, кв. 42"
    assert payload["items"][0]["unit_price"] == 12999000
    assert payload["items"][0]["product_title"] == "iPhone 15 Pro Max"
    assert payload["items"][0]["sku_name"] == "256GB Black"
    assert payload["items"][1]["line_total"] == 12999000
