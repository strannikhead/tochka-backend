from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from b2b.src.db import get_session
from b2b.src.main import app
from b2b.src.models import Product, ProductStatus


class FakeResult:
    def __init__(self, *, scalar_value: int | None = None, rows: list[tuple] | None = None) -> None:
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar_one(self) -> int:
        if self._scalar_value is None:
            raise ValueError("scalar_value is not set")
        return self._scalar_value

    def all(self) -> list[tuple]:
        return self._rows


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self._results = results

    async def execute(self, _stmt):
        return self._results.pop(0)


@pytest.fixture()
def client() -> Generator[TestClient]:
    app.dependency_overrides = {}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


def test__search_uses_db_session(client: TestClient) -> None:
    product = Product(
        id=UUID("770e8400-e29b-41d4-a716-446655440001"),
        title="iPhone 15 Pro Max",
        description="Flagship smartphone",
        status=ProductStatus.MODERATED,
        category_id=UUID("2c4e1c32-9e37-4c86-9e5a-0d3a6fa3b4c1"),
        images=[{"url": "https://example.com/item.jpg"}],
        characteristics=[{"name": "brand", "value": "Apple"}],
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )

    fake_session = FakeSession(
        [
            FakeResult(scalar_value=1),
            FakeResult(rows=[(product, 5, 129990)]),
        ]
    )

    async def override_get_session():
        yield fake_session

    app.dependency_overrides[get_session] = override_get_session

    response = client.get("/api/v1/products", params={"search": "iphone"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert payload["items"][0]["id"] == "770e8400-e29b-41d4-a716-446655440001"
