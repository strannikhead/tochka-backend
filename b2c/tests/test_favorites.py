from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_current_user_id
from api.favorites.dependencies import get_favorite_repository
from api.products.dependencies import get_product_repository
from favorites.repository import InMemoryFavoriteRepository
from main import app
from product_card.domain import Characteristic, Image, Product, ProductStatus, Sku
from product_card.repository import ProductRepository

TEST_USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_USER_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
PRODUCT_ID = UUID("770e8400-e29b-41d4-a716-446655440002")
BLOCKED_PRODUCT_ID = UUID("770e8400-e29b-41d4-a716-446655440099")


class StubProductRepository:
    def __init__(self, products: dict[UUID, Product]) -> None:
        self._products = products

    async def get_product(self, product_id: UUID) -> Product | None:
        return self._products.get(product_id)


def _build_product(product_id: UUID, status: ProductStatus) -> Product:
    images = (Image(url="https://example.com/img.jpg", order=1),)
    characteristics = (Characteristic(name="BRAND", value="Test"),)
    skus = (
        Sku(
            id=UUID("660e8400-e29b-41d4-a716-446655440001"),
            name="Test SKU",
            price=10000,
            discount=0,
            quantity=5,
            characteristics=characteristics,
            images=images,
        ),
    )
    return Product(
        id=product_id,
        slug="test-product",
        title="Test Product",
        description="A test product",
        images=images,
        status=status,
        characteristics=characteristics,
        skus=skus,
    )


@pytest.fixture()
def favorites_repo() -> InMemoryFavoriteRepository:
    return InMemoryFavoriteRepository()


@pytest.fixture()
def client(favorites_repo: InMemoryFavoriteRepository) -> Generator[TestClient]:
    product = _build_product(PRODUCT_ID, ProductStatus.MODERATED)
    stub_repo = StubProductRepository({product.id: product})

    app.dependency_overrides[get_favorite_repository] = lambda: favorites_repo
    app.dependency_overrides[get_product_repository] = lambda: stub_repo
    app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID

    with TestClient(app) as tc:
        yield tc

    app.dependency_overrides = {}


@pytest.fixture()
def client_blocked(favorites_repo: InMemoryFavoriteRepository) -> Generator[TestClient]:
    blocked = _build_product(BLOCKED_PRODUCT_ID, ProductStatus.BLOCKED)
    stub_repo = StubProductRepository({blocked.id: blocked})

    app.dependency_overrides[get_favorite_repository] = lambda: favorites_repo
    app.dependency_overrides[get_product_repository] = lambda: stub_repo
    app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID

    with TestClient(app) as tc:
        yield tc

    app.dependency_overrides = {}


def test_add_to_favorites_returns_201(client: TestClient) -> None:
    response = client.post(f"/api/v1/favorites/{PRODUCT_ID}")

    assert response.status_code == 201
    payload = response.json()
    assert payload["product_id"] == str(PRODUCT_ID)
    assert payload["user_id"] == str(TEST_USER_ID)
    assert "added_at" in payload
    assert payload["message"] == "Товар добавлен в избранное"


def test_repeat_add_returns_200_not_duplicate(client: TestClient) -> None:
    client.post(f"/api/v1/favorites/{PRODUCT_ID}")
    response = client.post(f"/api/v1/favorites/{PRODUCT_ID}")

    assert response.status_code == 200
    assert response.json()["message"] == "Товар уже находится в избранном"

    get_response = client.get("/api/v1/favorites")
    assert get_response.status_code == 200
    assert get_response.json()["total"] == 1
    assert len(get_response.json()["items"]) == 1


def test_blocked_product_excluded_from_list(client_blocked: TestClient) -> None:
    client_blocked.post(f"/api/v1/favorites/{BLOCKED_PRODUCT_ID}")
    response = client_blocked.get("/api/v1/favorites")

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


def test_user_id_from_query_is_ignored(client: TestClient) -> None:
    client.post(f"/api/v1/favorites/{PRODUCT_ID}")

    # user_id в query должен игнорироваться — берётся из JWT (переопределённый в тесте)
    response = client.get(f"/api/v1/favorites?user_id={OTHER_USER_ID}")

    assert response.status_code == 200
    # JWT-пользователь (TEST_USER_ID) имеет 1 избранный товар; OTHER_USER_ID — 0
    assert response.json()["total"] == 1
