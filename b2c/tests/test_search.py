from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from src.api.catalog.dependencies import get_catalog_repository
from src.catalog.repository import CatalogProduct, InMemoryCatalogRepository
from src.main import app

CATEGORY_ID = UUID("123e4567-e89b-12d3-a456-426614174001")


@pytest.fixture()
def client() -> Generator[TestClient]:
    app.dependency_overrides = {}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


def build_product(
    *,
    product_id: UUID,
    category_id: UUID,
    title: str,
    description: str = "Sample description",
    brand: str,
    color: str,
    price: int,
    rating: float,
    popularity: int,
) -> CatalogProduct:
    return CatalogProduct(
        id=product_id,
        title=title,
        description=description,
        image="https://example.com/images/item.jpg",
        price=price,
        in_stock=True,
        is_in_cart=False,
        category_id=category_id,
        attributes={"brand": brand, "color": color},
        rating=rating,
        popularity=popularity,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        discount=0,
    )


def override_repository(repository: InMemoryCatalogRepository) -> None:
    app.dependency_overrides[get_catalog_repository] = lambda: repository


def test__search_returns__matching_products(client: TestClient) -> None:
    products = [
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440030"),
            category_id=CATEGORY_ID,
            title="iPhone 15",
            description="Flagship Apple smartphone",
            brand="Apple",
            color="Black",
            price=100,
            rating=4.9,
            popularity=100,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440031"),
            category_id=CATEGORY_ID,
            title="Leather Case",
            description="Case for iPhone 15",
            brand="Apple",
            color="Brown",
            price=50,
            rating=4.5,
            popularity=80,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440032"),
            category_id=CATEGORY_ID,
            title="Galaxy",
            description="Samsung phone",
            brand="Samsung",
            color="White",
            price=90,
            rating=4.4,
            popularity=70,
        ),
    ]
    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get("/api/v1/products", params={"search": "iphone"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 2
    assert {item["id"] for item in payload["items"]} == {
        "770e8400-e29b-41d4-a716-446655440030",
        "770e8400-e29b-41d4-a716-446655440031",
    }


def test__short_query__returns_400(client: TestClient) -> None:
    repository = InMemoryCatalogRepository(products=[], categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get("/api/v1/products", params={"search": "ip"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["message"] == "Search query must be at least 3 characters"


def test__special_chars__do_not_break_query(client: TestClient) -> None:
    repository = InMemoryCatalogRepository(products=[], categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get("/api/v1/products", params={"search": "iPhone%15"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total_count"] == 0


def test__empty_results__returns_200(client: TestClient) -> None:
    products = [
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440040"),
            category_id=CATEGORY_ID,
            title="Coffee Grinder",
            description="Makes espresso",
            brand="Brew",
            color="Black",
            price=100,
            rating=4.0,
            popularity=50,
        )
    ]
    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get("/api/v1/products", params={"search": "headphones"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total_count"] == 0
