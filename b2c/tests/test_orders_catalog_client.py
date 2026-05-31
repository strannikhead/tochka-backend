from uuid import UUID

import pytest
from src.orders.domain import ReserveRequestItem
from src.orders.repository import HttpCheckoutCatalogClient


class RecordingCatalogClient(HttpCheckoutCatalogClient):
    def __init__(self) -> None:
        super().__init__(base_url="http://b2b", service_key="test-key")
        self.recorded_path: str | None = None
        self.recorded_payload: dict[str, object] | None = None
        self.recorded_expected_statuses: set[int] | None = None

    async def _post(
        self,
        path: str,
        payload: dict[str, object],
        *,
        expected_statuses: set[int] | None = None,
    ) -> dict[str, object]:
        self.recorded_path = path
        self.recorded_payload = payload
        self.recorded_expected_statuses = expected_statuses

        if path == "/api/v1/inventory/fulfill":
            return {
                "order_id": payload["order_id"],
                "status": "FULFILLED",
                "processed_at": "2026-05-31T00:00:00Z",
            }

        return {"reserved": True}


@pytest.mark.asyncio
async def test_reserve_uses_inventory_reserve_path() -> None:
    client = RecordingCatalogClient()

    result = await client.reserve(
        order_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        idempotency_key=UUID("550e8400-e29b-41d4-a716-446655440001"),
        items=[ReserveRequestItem(sku_id=UUID("550e8400-e29b-41d4-a716-446655440002"), quantity=1)],
    )

    assert result.reserved is True
    assert client.recorded_path == "/api/v1/inventory/reserve"


@pytest.mark.asyncio
async def test_fulfill_uses_inventory_fulfill_path() -> None:
    client = RecordingCatalogClient()

    await client.fulfill(
        order_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        items=[ReserveRequestItem(sku_id=UUID("550e8400-e29b-41d4-a716-446655440002"), quantity=1)],
    )

    assert client.recorded_path == "/api/v1/inventory/fulfill"
    assert client.recorded_expected_statuses == {200}
    assert client.recorded_payload == {
        "order_id": "550e8400-e29b-41d4-a716-446655440000",
        "items": [
            {
                "sku_id": "550e8400-e29b-41d4-a716-446655440002",
                "quantity": 1,
            }
        ],
    }
