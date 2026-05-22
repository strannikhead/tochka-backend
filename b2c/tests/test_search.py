from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from b2c.src.api.catalog.dependencies import get_catalog_repository
from b2c.src.catalog.repository import CatalogProduct, InMemoryCatalogRepository
from b2c.src.main import app

CATEGORY_ID = UUID("123e4567-e89b-12d3-a456-426614174010")


@pytest.fixture()
def client() -> Generator[TestClient]:
    app.dependency_overrides = {}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


def override_repository(repository: InMemoryCatalogRepository) -> None:
    app.dependency_overrides[get_catalog_repository] = lambda: repository


def build_product(
    *,
    product_id: UUID,
    title: str,
    description: str | None,
) -> CatalogProduct:
    return CatalogProduct(
        id=product_id,
        title=title,
        image="https://example.com/images/item.jpg",
        price=100,
        in_stock=True,
        is_in_cart=False,
        category_id=CATEGORY_ID,
        attributes={"brand": "Demo", "color": "Black"},
        rating=4.5,
        popularity=100,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        discount=0,
        description=description,
    )


def test_search_returns_matching_products(client: TestClient) -> None:
    products = [
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440101"),
            title="Wireless Headphones",
            description="Noise cancelling",
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440102"),
            title="Laptop Pro",
            description="Includes wireless mouse",
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440103"),
            title="Wired Mouse",
            description="Basic accessory",
        ),
    ]
    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get("/api/v1/catalog/products", params={"q": "wireless"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 2
    assert {item["id"] for item in payload["items"]} == {
        "770e8400-e29b-41d4-a716-446655440101",
        "770e8400-e29b-41d4-a716-446655440102",
    }
    assert payload["items"][0]["name"]
    assert payload["items"][0]["images"]


def test_short_query_returns_400(client: TestClient) -> None:
    repository = InMemoryCatalogRepository()
    override_repository(repository)

    response = client.get("/api/v1/catalog/products", params={"q": "ip"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "INVALID_REQUEST"
    assert payload["message"] == "Search query must be at least 3 characters"


def test_special_chars_do_not_break_query(client: TestClient) -> None:
    products = [
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440201"),
            title="iPhone 15 Pro",
            description="Flagship smartphone",
        )
    ]
    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get("/api/v1/catalog/products", params={"q": "iPhone%15"})

    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload


def test_empty_results_returns_200(client: TestClient) -> None:
    products = [
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440301"),
            title="Phone",
            description="Basic device",
        )
    ]
    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get("/api/v1/catalog/products", params={"q": "nonexistent"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total_count"] == 0


def test_long_query_returns_400(client: TestClient) -> None:
    repository = InMemoryCatalogRepository()
    override_repository(repository)

    response = client.get("/api/v1/catalog/products", params={"q": "x" * 201})

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "INVALID_REQUEST"
    assert payload["message"] == "Search query must be at most 200 characters"
