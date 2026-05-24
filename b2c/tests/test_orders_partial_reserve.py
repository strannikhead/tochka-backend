from uuid import UUID

from tests.order_test_utils import auth_header


def test_partial_reserve_failure_returns_409(client):
    sku_id = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")
    failing_sku_id = UUID("8a4e3f9c-1a2b-4c8d-9e5f-6b7a8c9d0e1f")

    response = client.post(
        "/api/v1/orders",
        headers=auth_header(UUID("111e8400-e29b-41d4-a716-446655440000")),
        json={
            "idempotency_key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "items": [
                {"sku_id": str(sku_id), "quantity": 1},
                {"sku_id": str(failing_sku_id), "quantity": 5},
            ],
        },
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "RESERVE_FAILED"
    assert payload["failed_items"][0]["sku_id"] == str(failing_sku_id)
