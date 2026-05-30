from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from src.api.dependencies import get_current_user_id
from src.api.favorites.dependencies import get_favorite_repository
from src.api.products.dependencies import get_product_repository
from src.favorites.repository import InMemoryFavoriteRepository
from src.main import app
from src.product_card.domain import Characteristic, Image, Product, ProductStatus, Sku
from src.product_card.repository import UpstreamServiceError

TEST_USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_USER_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
PRODUCT_ID = UUID("770e8400-e29b-41d4-a716-446655440002")
BLOCKED_PRODUCT_ID = UUID("770e8400-e29b-41d4-a716-446655440099")
MISSING_PRODUCT_ID = UUID("770e8400-e29b-41d4-a716-4466554400ff")


class StubProductRepository:
    def __init__(self, products: dict[UUID, Product]) -> None:
        self._products = products

    async def get_product(self, product_id: UUID) -> Product | None:
        return self._products.get(product_id)

    async def get_similar_products(self, product_id: UUID, limit: int) -> list[Product]:
        return []


def _build_product(product_id: UUID, status: ProductStatus) -> Product:
    image = Image(
        id=UUID("111e8400-e29b-41d4-a716-446655440000"),
        url="https://example.com/img.jpg",
        ordering=1,
    )
    characteristic = Characteristic(name="BRAND", value="Test")
    sku = Sku(
        id=UUID("660e8400-e29b-41d4-a716-446655440001"),
        product_id=product_id,
        name="Test SKU",
        sku_code="TST-001",
        price=10000,
        discount=0,
        stock_quantity=5,
        active_quantity=5,
        characteristics=(characteristic,),
        images=(image,),
    )
    return Product(
        id=product_id,
        name="Test Product",
        slug="test-product",
        description="A test product",
        images=(image,),
        status=status,
        characteristics=(characteristic,),
        skus=(sku,),
        min_price=10000,
    )


@pytest.fixture()
def favorites_repo() -> InMemoryFavoriteRepository:
    return InMemoryFavoriteRepository()


def _make_client(
    favorites_repo: InMemoryFavoriteRepository,
    products: dict[UUID, Product],
) -> Generator[TestClient]:
    stub_repo = StubProductRepository(products)

    app.dependency_overrides[get_favorite_repository] = lambda: favorites_repo
    app.dependency_overrides[get_product_repository] = lambda: stub_repo
    app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID

    with TestClient(app) as tc:
        yield tc

    app.dependency_overrides = {}


@pytest.fixture()
def client(favorites_repo: InMemoryFavoriteRepository) -> Generator[TestClient]:
    product = _build_product(PRODUCT_ID, ProductStatus.MODERATED)
    yield from _make_client(favorites_repo, {product.id: product})


@pytest.fixture()
def client_blocked(favorites_repo: InMemoryFavoriteRepository) -> Generator[TestClient]:
    blocked = _build_product(BLOCKED_PRODUCT_ID, ProductStatus.BLOCKED)
    yield from _make_client(favorites_repo, {blocked.id: blocked})


def test_add_to_favorites_returns_204(client: TestClient) -> None:
    response = client.put(f"/api/v1/favorites/{PRODUCT_ID}")

    assert response.status_code == 204
    assert response.content == b""


def test_repeat_add_returns_204_idempotent(client: TestClient) -> None:
    first = client.put(f"/api/v1/favorites/{PRODUCT_ID}")
    second = client.put(f"/api/v1/favorites/{PRODUCT_ID}")

    assert first.status_code == 204
    assert second.status_code == 204

    listing = client.get("/api/v1/favorites")
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["total_count"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == str(PRODUCT_ID)


def test_blocked_product_excluded_from_list(client_blocked: TestClient) -> None:
    client_blocked.put(f"/api/v1/favorites/{BLOCKED_PRODUCT_ID}")
    response = client_blocked.get("/api/v1/favorites")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 0
    assert payload["items"] == []


def test_user_id_from_query_is_ignored(client: TestClient) -> None:
    client.put(f"/api/v1/favorites/{PRODUCT_ID}")

    # user_id в query должен игнорироваться — берётся из JWT (переопределённый в тесте)
    response = client.get(f"/api/v1/favorites?user_id={OTHER_USER_ID}")

    assert response.status_code == 200
    # JWT-пользователь (TEST_USER_ID) имеет 1 избранный товар; OTHER_USER_ID — 0
    assert response.json()["total_count"] == 1


def test_add_nonexistent_product_returns_404(client: TestClient) -> None:
    response = client.put(f"/api/v1/favorites/{MISSING_PRODUCT_ID}")

    assert response.status_code == 404


def test_delete_nonexistent_is_idempotent(client: TestClient) -> None:
    response = client.delete(f"/api/v1/favorites/{MISSING_PRODUCT_ID}")

    assert response.status_code == 204


class _FailingProductRepository:
    async def get_product(self, product_id: UUID) -> Product | None:
        raise UpstreamServiceError("b2b unavailable", status_code=503)

    async def get_similar_products(self, product_id: UUID, limit: int) -> list[Product]:
        return []


def test_list_favorites_upstream_error_uses_code_message_schema(
    favorites_repo: InMemoryFavoriteRepository,
) -> None:
    """GET /favorites должен возвращать ошибку в формате Error из openapi.yaml: {code, message}."""

    async def _seed() -> None:
        await favorites_repo.add_favorite(TEST_USER_ID, PRODUCT_ID)

    import asyncio

    asyncio.run(_seed())

    app.dependency_overrides[get_favorite_repository] = lambda: favorites_repo
    app.dependency_overrides[get_product_repository] = lambda: _FailingProductRepository()
    app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID

    try:
        with TestClient(app) as tc:
            response = tc.get("/api/v1/favorites")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 503
    body = response.json()
    assert set(body.keys()) >= {"code", "message"}
    assert isinstance(body["code"], str) and body["code"]
    assert isinstance(body["message"], str) and body["message"]
    assert "detail" not in body
