from uuid import UUID

from tests.order_test_utils import auth_header


def test_idempotency_returns_existing_order(client):
    sku_id = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")

    payload = {
        "idempotency_key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "items": [{"sku_id": str(sku_id), "quantity": 1}],
    }

    first_response = client.post(
        "/api/v1/orders",
        headers=auth_header(UUID("111e8400-e29b-41d4-a716-446655440000")),
        json=payload,
    )
    second_response = client.post(
        "/api/v1/orders",
        headers=auth_header(UUID("111e8400-e29b-41d4-a716-446655440000")),
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 200
    assert second_response.json()["id"] == first_response.json()["id"]
    assert second_response.json()["items"][0]["unit_price"] == 12999000
