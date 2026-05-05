from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from src.api.catalog.dependencies import get_catalog_repository
from src.catalog.repository import CatalogProduct, InMemoryCatalogRepository, UpstreamServiceError
from src.main import app

CATEGORY_ID = UUID("123e4567-e89b-12d3-a456-426614174001")
OTHER_CATEGORY_ID = UUID("123e4567-e89b-12d3-a456-426614174002")


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
    brand: str,
    color: str,
    price: int,
    rating: float,
    popularity: int,
) -> CatalogProduct:
    return CatalogProduct(
        id=product_id,
        title=title,
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


def test__catalog_filters__returns_only_filtered_products(client: TestClient) -> None:
    products = [
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440010"),
            category_id=CATEGORY_ID,
            title="iPhone 15",
            brand="Apple",
            color="Black",
            price=100,
            rating=4.9,
            popularity=100,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440011"),
            category_id=CATEGORY_ID,
            title="iPhone 14",
            brand="Apple",
            color="White",
            price=200,
            rating=4.7,
            popularity=90,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440012"),
            category_id=CATEGORY_ID,
            title="Galaxy",
            brand="Samsung",
            color="Black",
            price=50,
            rating=4.6,
            popularity=120,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440013"),
            category_id=OTHER_CATEGORY_ID,
            title="iPhone 13",
            brand="Apple",
            color="Black",
            price=80,
            rating=4.5,
            popularity=80,
        ),
    ]
    repository = InMemoryCatalogRepository(
        products=products, categories={CATEGORY_ID, OTHER_CATEGORY_ID}
    )
    override_repository(repository)

    response = client.get(
        "/api/v1/products",
        params={
            "category_id": str(CATEGORY_ID),
            "filters[brand]": "Apple",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 2
    items = payload["items"]
    assert {item["id"] for item in items} == {
        "770e8400-e29b-41d4-a716-446655440010",
        "770e8400-e29b-41d4-a716-446655440011",
    }


def test__catalog_sorting__orders_by_price_asc(client: TestClient) -> None:
    products = [
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440010"),
            category_id=CATEGORY_ID,
            title="iPhone 15",
            brand="Apple",
            color="Black",
            price=100,
            rating=4.9,
            popularity=100,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440011"),
            category_id=CATEGORY_ID,
            title="iPhone 14",
            brand="Apple",
            color="White",
            price=200,
            rating=4.7,
            popularity=90,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440012"),
            category_id=CATEGORY_ID,
            title="Galaxy",
            brand="Samsung",
            color="Black",
            price=50,
            rating=4.6,
            popularity=120,
        ),
    ]
    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get(
        "/api/v1/products",
        params={
            "category_id": str(CATEGORY_ID),
            "sort": "price_asc",
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [
        "770e8400-e29b-41d4-a716-446655440012",
        "770e8400-e29b-41d4-a716-446655440010",
        "770e8400-e29b-41d4-a716-446655440011",
    ]


def test__catalog_pagination__applies_limit_and_offset(client: TestClient) -> None:
    products = [
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440010"),
            category_id=CATEGORY_ID,
            title="iPhone 15",
            brand="Apple",
            color="Black",
            price=100,
            rating=4.9,
            popularity=100,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440011"),
            category_id=CATEGORY_ID,
            title="iPhone 14",
            brand="Apple",
            color="White",
            price=200,
            rating=4.7,
            popularity=90,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440012"),
            category_id=CATEGORY_ID,
            title="Galaxy",
            brand="Samsung",
            color="Black",
            price=50,
            rating=4.6,
            popularity=120,
        ),
    ]
    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get(
        "/api/v1/products",
        params={
            "category_id": str(CATEGORY_ID),
            "sort": "price_asc",
            "limit": 1,
            "offset": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 3
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == "770e8400-e29b-41d4-a716-446655440010"


def test__facets_apply_filters(client: TestClient) -> None:
    products = [
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440020"),
            category_id=CATEGORY_ID,
            title="iPhone 15",
            brand="Apple",
            color="Black",
            price=100,
            rating=4.9,
            popularity=100,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440021"),
            category_id=CATEGORY_ID,
            title="iPhone 14",
            brand="Apple",
            color="White",
            price=200,
            rating=4.7,
            popularity=90,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440022"),
            category_id=CATEGORY_ID,
            title="Galaxy",
            brand="Samsung",
            color="Black",
            price=50,
            rating=4.6,
            popularity=120,
        ),
    ]
    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get(
        "/api/v1/catalog/facets",
        params={
            "category_id": str(CATEGORY_ID),
            "filters[brand]": "Apple",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["category_id"] == str(CATEGORY_ID)
    facets = {facet["name"]: facet["values"] for facet in payload["facets"]}
    brand_values = {item["value"]: item["count"] for item in facets["brand"]}
    color_values = {item["value"]: item["count"] for item in facets["color"]}
    assert brand_values == {"Apple": 2}
    assert color_values == {"Black": 1, "White": 1}


def test__facets_return__counts_per_filter_value(client: TestClient) -> None:
    products = [
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440020"),
            category_id=CATEGORY_ID,
            title="iPhone 15",
            brand="Apple",
            color="Black",
            price=100,
            rating=4.9,
            popularity=100,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440021"),
            category_id=CATEGORY_ID,
            title="iPhone 14",
            brand="Apple",
            color="White",
            price=200,
            rating=4.7,
            popularity=90,
        ),
        build_product(
            product_id=UUID("770e8400-e29b-41d4-a716-446655440022"),
            category_id=CATEGORY_ID,
            title="Galaxy",
            brand="Samsung",
            color="Black",
            price=50,
            rating=4.6,
            popularity=120,
        ),
    ]
    repository = InMemoryCatalogRepository(products=products, categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get(
        "/api/v1/catalog/facets",
        params={
            "category_id": str(CATEGORY_ID),
        },
    )

    assert response.status_code == 200
    facets = {facet["name"]: facet["values"] for facet in response.json()["facets"]}
    brand_values = {item["value"]: item["count"] for item in facets["brand"]}
    color_values = {item["value"]: item["count"] for item in facets["color"]}
    assert brand_values == {"Apple": 2, "Samsung": 1}
    assert color_values == {"Black": 2, "White": 1}


def test__invalid_sort__returns_400(client: TestClient) -> None:
    repository = InMemoryCatalogRepository(products=[], categories={CATEGORY_ID})
    override_repository(repository)

    response = client.get("/api/v1/products", params={"sort": "unknown"})

    assert response.status_code == 400
    assert "Invalid sort parameter" in response.json()["message"]


def test__b2b_unavailable__returns_502(client: TestClient) -> None:
    class UnavailableCatalogRepository(InMemoryCatalogRepository):
        async def list_products(  # type: ignore[override]
            self,
            *,
            category_id: UUID | None,
            filters: dict[str, list[str]] | None,
            sort: str | None,
            limit: int,
            offset: int,
            search: str | None,
        ) -> object:
            raise UpstreamServiceError("B2B temporarily unavailable", None)

    override_repository(UnavailableCatalogRepository(products=[], categories=set()))

    response = client.get("/api/v1/products")

    assert response.status_code == 502
    assert response.json()["message"] == "B2B temporarily unavailable"
