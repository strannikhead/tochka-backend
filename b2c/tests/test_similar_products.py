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


def build_product(*, product_id: UUID, category_id: UUID, title: str) -> CatalogProduct:
    return CatalogProduct(
        id=product_id,
        title=title,
        description="Sample description",
        image="https://example.com/images/item.jpg",
        price=100,
        in_stock=True,
        is_in_cart=False,
        category_id=category_id,
        attributes={"brand": "Brand", "color": "Black"},
        rating=4.5,
        popularity=100,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        discount=0,
    )


def override_repository(repository: InMemoryCatalogRepository) -> None:
    app.dependency_overrides[get_catalog_repository] = lambda: repository


def test__similar__returns_up_to_8_from_same_category(client: TestClient) -> None:
    current_id = UUID("770e8400-e29b-41d4-a716-446655440110")
    products = [
        build_product(product_id=current_id, category_id=CATEGORY_ID, title="Current"),
    ]
    for index in range(1, 10):
        products.append(
            build_product(
                product_id=UUID(f"770e8400-e29b-41d4-a716-44665544011{index}"),
                category_id=CATEGORY_ID,
                title=f"Item {index}",
            )
        )

    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get(
        f"/api/v1/products/{current_id}/similar",
        params={"category": str(CATEGORY_ID)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 9
    ids = {item["id"] for item in payload["items"]}
    assert len(ids) <= 8
    assert str(current_id) not in ids
    expected_ids = {str(product.id) for product in products if product.id != current_id}
    assert ids.issubset(expected_ids)


def test__similar__respects_limit(client: TestClient) -> None:
    current_id = UUID("770e8400-e29b-41d4-a716-446655440210")
    products = [
        build_product(product_id=current_id, category_id=CATEGORY_ID, title="Current"),
    ]
    for index in range(1, 11):
        products.append(
            build_product(
                product_id=UUID(f"770e8400-e29b-41d4-a716-4466554403{index:02d}"),
                category_id=CATEGORY_ID,
                title=f"Item {index}",
            )
        )

    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get(
        f"/api/v1/products/{current_id}/similar",
        params={"category": str(CATEGORY_ID), "limit": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 3
    assert len(payload["items"]) == 3
    assert payload["total_count"] == 10


def test__similar__respects_offset(client: TestClient) -> None:
    current_id = UUID("770e8400-e29b-41d4-a716-446655440310")
    products = [
        build_product(product_id=current_id, category_id=CATEGORY_ID, title="Current"),
    ]
    for index in range(1, 11):
        products.append(
            build_product(
                product_id=UUID(int=current_id.int + index),
                category_id=CATEGORY_ID,
                title=f"Item {index}",
            )
        )

    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get(
        f"/api/v1/products/{current_id}/similar",
        params={"category": str(CATEGORY_ID), "limit": 4, "offset": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 4
    assert payload["offset"] == 3
    assert len(payload["items"]) == 4
    assert payload["total_count"] == 10


def test__similar__empty_category_returns_200_empty_list(client: TestClient) -> None:
    current_id = UUID("770e8400-e29b-41d4-a716-446655440120")
    products = [build_product(product_id=current_id, category_id=CATEGORY_ID, title="Only")]
    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get(
        f"/api/v1/products/{current_id}/similar",
        params={"category": str(CATEGORY_ID)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total_count"] == 0


def test__similar__unknown_product_returns_404(client: TestClient) -> None:
    products = [
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440130"),
            category_id=CATEGORY_ID,
            title="Known",
        )
    ]
    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get(
        "/api/v1/products/770e8400-e29b-41d4-a716-446655440999/similar",
        params={"category": str(CATEGORY_ID)},
    )

    assert response.status_code == 404
