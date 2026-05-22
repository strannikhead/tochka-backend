from collections.abc import Generator
from datetime import UTC, datetime
from re import findall, search
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Select

from b2b.src.main import app
from b2b.src.models import SKU, Category, Product, ProductStatus
from b2b.src.public_catalog.application.service import PublicCatalogService
from b2b.src.public_catalog.dependencies import get_public_catalog_service


class FakeResult:
    def __init__(self, rows: list[tuple[Product, int]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[Product, int]]:
        return self._rows


class FakeSession:
    def __init__(self, products: list[Product], categories: list[Category]) -> None:
        self._products = products
        self._categories = {category.id: category for category in categories}

    async def get(self, model: type, identity: UUID):
        if model is Product:
            return next((product for product in self._products if product.id == identity), None)
        if model is Category:
            return self._categories.get(identity)
        raise AssertionError(f"Unsupported model: {model!r}")

    async def execute(self, statement: Select) -> FakeResult:
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        category_match = search(r"products\.category_id = '([0-9a-f-]+)'", sql)
        assert category_match is not None
        category_id = UUID(category_match.group(1))

        limit_clause = getattr(statement, "_limit_clause", None)
        limit = int(getattr(limit_clause, "value", 0) or 0)

        excluded_ids: set[UUID] = set()
        exclude_match = search(r"products\.id NOT IN \((.*?)\)", sql)
        if exclude_match is not None:
            excluded_ids = {
                UUID(value) for value in findall(r"'([0-9a-f-]+)'", exclude_match.group(1))
            }

        rows = [
            (
                product,
                min(sku.price for sku in product.skus if sku.active_quantity > 0),
            )
            for product in self._products
            if product.category_id == category_id
            and product.status == ProductStatus.MODERATED
            and any(sku.active_quantity > 0 for sku in product.skus)
            and product.id not in excluded_ids
        ]
        if limit > 0:
            rows = rows[:limit]
        return FakeResult(rows)


def _make_category(category_id: str, parent_id: str | None = None) -> Category:
    return Category(
        id=UUID(category_id),
        name=f"Category {category_id[-4:]}",
        parent_id=UUID(parent_id) if parent_id is not None else None,
        level=0,
        path=f"/{category_id}",
        is_active=True,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def _make_product(product_id: str, category_id: str, price: int) -> Product:
    product = Product(
        id=UUID(product_id),
        title=f"Product {product_id[-4:]}",
        description="Description",
        status=ProductStatus.MODERATED,
        category_id=UUID(category_id),
        images=[{"url": f"https://cdn.example.com/{product_id}.jpg"}],
        characteristics=[],
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    product.skus = [
        SKU(
            id=UUID(f"{product_id[:8]}-0000-4000-8000-000000000001"),
            product_id=UUID(product_id),
            name="Default SKU",
            price=price,
            active_quantity=1,
            images=[],
            characteristics=[],
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
    ]
    return product


@pytest.fixture()
def client() -> Generator[TestClient]:
    app.dependency_overrides = {}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


def test__similar_returns_up_to_8_from_same_category(client: TestClient) -> None:
    current_id = "770e8400-e29b-41d4-a716-446655440010"
    main_category_id = "550e8400-e29b-41d4-a716-446655440010"
    products = [
        _make_product(current_id, main_category_id, 1000),
    ] + [
        _make_product(f"770e8400-e29b-41d4-a716-4466554400{i:02d}", main_category_id, 1000 + i)
        for i in range(1, 11)
    ]
    categories = [_make_category(main_category_id)]
    session = FakeSession(products, categories)
    app.dependency_overrides[get_public_catalog_service] = lambda: PublicCatalogService(session)

    response = client.get(
        f"/api/v1/public/products/{current_id}/similar",
        params={"limit": 8},
        headers={"X-Service-Key": "dev-service-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 8
    assert current_id not in {item["id"] for item in payload}


def test__empty_category_returns_200_empty_list(client: TestClient) -> None:
    current_id = "770e8400-e29b-41d4-a716-446655440020"
    main_category_id = "550e8400-e29b-41d4-a716-446655440020"
    products = [_make_product(current_id, main_category_id, 1000)]
    categories = [_make_category(main_category_id)]
    session = FakeSession(products, categories)
    app.dependency_overrides[get_public_catalog_service] = lambda: PublicCatalogService(session)

    response = client.get(
        f"/api/v1/public/products/{current_id}/similar",
        params={"limit": 8},
        headers={"X-Service-Key": "dev-service-key"},
    )

    assert response.status_code == 200
    assert response.json() == []


def test__fallback_to_parent_category_fills_limit(client: TestClient) -> None:
    current_id = "770e8400-e29b-41d4-a716-446655440030"
    main_category_id = "550e8400-e29b-41d4-a716-446655440030"
    parent_category_id = "550e8400-e29b-41d4-a716-446655440031"
    products = [
        _make_product(current_id, main_category_id, 1000),
        _make_product("770e8400-e29b-41d4-a716-446655440031", main_category_id, 1001),
        _make_product("770e8400-e29b-41d4-a716-446655440032", main_category_id, 1002),
        _make_product("770e8400-e29b-41d4-a716-446655440033", main_category_id, 1003),
    ] + [
        _make_product(f"770e8400-e29b-41d4-a716-4466554401{i:02d}", parent_category_id, 1100 + i)
        for i in range(1, 11)
    ]
    categories = [
        _make_category(main_category_id, parent_id=parent_category_id),
        _make_category(parent_category_id),
    ]
    session = FakeSession(products, categories)
    app.dependency_overrides[get_public_catalog_service] = lambda: PublicCatalogService(session)

    response = client.get(
        f"/api/v1/public/products/{current_id}/similar",
        params={"limit": 8},
        headers={"X-Service-Key": "dev-service-key"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 8
    assert any(item["id"].startswith("770e8400-e29b-41d4-a716-4466554401") for item in payload)


def test__unknown_product_returns_404(client: TestClient) -> None:
    categories = [_make_category("550e8400-e29b-41d4-a716-446655440040")]
    session = FakeSession([], categories)
    app.dependency_overrides[get_public_catalog_service] = lambda: PublicCatalogService(session)

    response = client.get(
        "/api/v1/public/products/770e8400-e29b-41d4-a716-446655440099/similar",
        headers={"X-Service-Key": "dev-service-key"},
    )

    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND", "message": "Product not found"}
