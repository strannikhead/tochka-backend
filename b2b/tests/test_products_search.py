from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from b2b.src.main import app
from b2b.src.products.dependencies import get_products_service
from b2b.src.products.domain.models import ProductListItem, ProductListResponse


class StubProductsService:
    def __init__(self, response: ProductListResponse, expected_search: str | None = None) -> None:
        self._response = response
        self._expected_search = expected_search

    async def list_products(
        self,
        *,
        category_id: UUID | None,
        filters: dict[str, list[str]],
        sort: str | None,
        limit: int,
        offset: int,
        search: str | None,
    ) -> ProductListResponse:
        if self._expected_search is not None:
            assert search == self._expected_search
        return self._response


@pytest.fixture()
def client() -> Generator[TestClient]:
    app.dependency_overrides = {}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


def test_search_returns_matching_products(client: TestClient) -> None:
    response_payload = ProductListResponse(
        items=(
            ProductListItem(
                id=UUID("770e8400-e29b-41d4-a716-446655441001"),
                title="Wireless Headphones",
                image="https://example.com/1.png",
                price=1200,
                in_stock=True,
                is_in_cart=False,
            ),
            ProductListItem(
                id=UUID("770e8400-e29b-41d4-a716-446655441002"),
                title="Laptop Pro",
                image="",
                price=2200,
                in_stock=True,
                is_in_cart=False,
            ),
        ),
        total_count=2,
        limit=20,
        offset=0,
    )
    app.dependency_overrides[get_products_service] = lambda: StubProductsService(
        response_payload, expected_search="wireless"
    )

    response = client.get("/api/v1/products", params={"search": "wireless"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 2
    assert {item["id"] for item in payload["items"]} == {
        "770e8400-e29b-41d4-a716-446655441001",
        "770e8400-e29b-41d4-a716-446655441002",
    }


def test_special_chars_do_not_break_query(client: TestClient) -> None:
    response_payload = ProductListResponse(items=(), total_count=0, limit=20, offset=0)
    app.dependency_overrides[get_products_service] = lambda: StubProductsService(
        response_payload, expected_search="iPhone%15"
    )

    response = client.get("/api/v1/products", params={"search": "iPhone%15"})

    assert response.status_code == 200
    assert "items" in response.json()
