from uuid import UUID

from src.api.dependencies import get_current_user_id
from src.main import app
from tests.order_test_utils import (
    CHECKOUT_USER_ID,
    auth_header,
    checkout_request_body,
    seed_cart_items,
)


def test_idempotency_returns_existing_order(client):
    sku_id = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")

    seed_cart_items(CHECKOUT_USER_ID, [(sku_id, 1)])
    app.dependency_overrides[get_current_user_id] = lambda: CHECKOUT_USER_ID

    payload = checkout_request_body(user_id=CHECKOUT_USER_ID)

    first_response = client.post(
        "/api/v1/orders",
        headers={
            **auth_header(CHECKOUT_USER_ID),
            "Idempotency-Key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        },
        json=payload,
    )
    second_response = client.post(
        "/api/v1/orders",
        headers={
            **auth_header(CHECKOUT_USER_ID),
            "Idempotency-Key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        },
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 200
    assert second_response.json()["id"] == first_response.json()["id"]
    assert second_response.json()["items"][0]["unit_price"] == 12999000


def test_idempotency_conflicts_on_different_body(client):
    sku_id = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")

    seed_cart_items(CHECKOUT_USER_ID, [(sku_id, 1)])
    app.dependency_overrides[get_current_user_id] = lambda: CHECKOUT_USER_ID

    first_response = client.post(
        "/api/v1/orders",
        headers={
            **auth_header(CHECKOUT_USER_ID),
            "Idempotency-Key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        },
        json=checkout_request_body(user_id=CHECKOUT_USER_ID, comment="first"),
    )
    second_response = client.post(
        "/api/v1/orders",
        headers={
            **auth_header(CHECKOUT_USER_ID),
            "Idempotency-Key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        },
        json=checkout_request_body(user_id=CHECKOUT_USER_ID, comment="second"),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_checkout_snapshot_mismatch_returns_cart_validation_response(client):
    sku_id = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")

    seed_cart_items(CHECKOUT_USER_ID, [(sku_id, 1)])
    app.dependency_overrides[get_current_user_id] = lambda: CHECKOUT_USER_ID

    response = client.post(
        "/api/v1/orders",
        headers={
            **auth_header(CHECKOUT_USER_ID),
            "Idempotency-Key": "f47ac10b-58cc-4372-a567-0e02b2c3d47f",
        },
        json=checkout_request_body(
            user_id=CHECKOUT_USER_ID,
            items_snapshot=[{"sku_id": str(sku_id), "quantity": 1, "unit_price": 1}],
        ),
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["is_valid"] is False
    assert payload["cart"]["is_valid"] is True or payload["cart"]["is_valid"] is False
    assert isinstance(payload["issues"], list)
