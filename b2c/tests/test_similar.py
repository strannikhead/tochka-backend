from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from b2c.src.api.catalog.dependencies import get_catalog_repository
from b2c.src.catalog.repository import CatalogRepository, UpstreamServiceError
from b2c.src.main import app


class FakeCatalogRepository(CatalogRepository):
    def __init__(self, items: list[dict[str, object]] | None = None) -> None:
        self._items = items or []
        self._raise_not_found = False

    def set_not_found(self) -> None:
        self._raise_not_found = True

    async def list_products(self, **_kwargs):  # type: ignore[override]
        raise NotImplementedError

    async def get_facets(self, **_kwargs):  # type: ignore[override]
        raise NotImplementedError

    async def get_similar(self, *, product_id: UUID, limit: int) -> list[dict[str, object]]:
        if self._raise_not_found:
            raise UpstreamServiceError("Product not found", 404)
        return self._items[:limit]


@pytest.fixture()
def client() -> Generator[TestClient]:
    app.dependency_overrides = {}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


def test__similar_returns_up_to_8_from_same_category(client: TestClient) -> None:
    current_id = "770e8400-e29b-41d4-a716-446655440010"
    items = [
        {
            "id": f"770e8400-e29b-41d4-a716-4466554400{i:02d}",
            "name": f"Item {i}",
            "min_price": 1000 + i,
            "has_stock": True,
            "images": [],
        }
        for i in range(1, 11)
        if f"770e8400-e29b-41d4-a716-4466554400{i:02d}" != current_id
    ]
    repository = FakeCatalogRepository(items)
    app.dependency_overrides[get_catalog_repository] = lambda: repository

    response = client.get(f"/api/v1/catalog/products/{current_id}/similar", params={"limit": 8})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 8
    assert current_id not in {item["id"] for item in payload}


def test__empty_category_returns_200_empty_list(client: TestClient) -> None:
    repository = FakeCatalogRepository([])
    app.dependency_overrides[get_catalog_repository] = lambda: repository

    response = client.get("/api/v1/catalog/products/770e8400-e29b-41d4-a716-446655440010/similar")

    assert response.status_code == 200
    assert response.json() == []


def test__unknown_product_returns_404(client: TestClient) -> None:
    repository = FakeCatalogRepository([])
    repository.set_not_found()
    app.dependency_overrides[get_catalog_repository] = lambda: repository

    response = client.get("/api/v1/catalog/products/770e8400-e29b-41d4-a716-446655440999/similar")

    assert response.status_code == 404
    assert response.json()["message"] == "Product not found"
