from uuid import UUID

from src.api.orders.dependencies import get_checkout_catalog_client
from src.main import app
from src.orders.repository import HttpCheckoutCatalogClient
from tests.order_test_utils import auth_header


def test_b2b_unavailable_returns_503(client):
    app.dependency_overrides[get_checkout_catalog_client] = lambda: HttpCheckoutCatalogClient(
        base_url="http://127.0.0.1:1"
    )

    sku_id = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")
    response = client.post(
        "/api/v1/orders",
        headers=auth_header(UUID("111e8400-e29b-41d4-a716-446655440000")),
        json={
            "idempotency_key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "items": [{"sku_id": str(sku_id), "quantity": 1}],
        },
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["code"] == "B2B_UNAVAILABLE"
