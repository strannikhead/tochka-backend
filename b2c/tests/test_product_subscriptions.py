from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from src.api.favorites.dependencies import (
    ProductNotFoundError,
    get_current_user_id,
    get_favorites_repository,
    get_product_client,
)
from src.main import app

USER_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
PRODUCT_ID = UUID("123e4567-e89b-12d3-a456-426614174001")
UNKNOWN_PRODUCT_ID = UUID("770e8400-e29b-41d4-a716-446655440999")


@dataclass
class SubscriptionRecord:
    id: UUID
    user_id: UUID
    product_id: UUID
    notify_on: list[str]
    created_at: datetime


class InMemoryFavoritesRepository:
    def __init__(self) -> None:
        self._subscriptions: dict[tuple[UUID, UUID], SubscriptionRecord] = {}

    async def get_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> SubscriptionRecord | None:
        return self._subscriptions.get((user_id, product_id))

    async def create_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
        notify_on: list[str],
    ) -> SubscriptionRecord:
        subscription = SubscriptionRecord(
            id=uuid4(),
            user_id=user_id,
            product_id=product_id,
            notify_on=notify_on,
            created_at=datetime.now(UTC),
        )
        self._subscriptions[(user_id, product_id)] = subscription
        return subscription

    async def delete_product_subscription(
        self,
        *,
        user_id: UUID,
        product_id: UUID,
    ) -> None:
        self._subscriptions.pop((user_id, product_id), None)


class StubProductClient:
    def __init__(self, products: dict[UUID, dict]) -> None:
        self._products = products

    async def get_product(self, product_id: UUID) -> dict:
        product = self._products.get(product_id)

        if product is None:
            raise ProductNotFoundError

        return product


@pytest.fixture()
def client() -> Generator[TestClient]:
    app.dependency_overrides = {}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


def build_product(product_id: UUID) -> dict:
    return {
        "id": str(product_id),
        "title": "iPhone 15 Pro Max",
        "description": "Sample product",
        "status": "MODERATED",
        "category": {
            "id": "123e4567-e89b-12d3-a456-426614174010",
            "name": "Smartphones",
        },
        "images": [],
        "characteristics": [],
        "skus": [],
    }


def override_dependencies(
    *,
    repository: InMemoryFavoritesRepository,
    product_client: StubProductClient | None = None,
    user_id: UUID = USER_ID,
) -> None:
    if product_client is None:
        product_client = StubProductClient({PRODUCT_ID: build_product(PRODUCT_ID)})

    app.dependency_overrides[get_favorites_repository] = lambda: repository
    app.dependency_overrides[get_product_client] = lambda: product_client
    app.dependency_overrides[get_current_user_id] = lambda: user_id


def test__subscribe_returns_201_with_notify_on(client: TestClient) -> None:
    repository = InMemoryFavoritesRepository()
    override_dependencies(repository=repository)

    response = client.post(
        f"/api/v1/favorites/{PRODUCT_ID}/subscribe",
        json={"notify_on": ["IN_STOCK", "PRICE_DOWN"]},
    )

    assert response.status_code == 201

    payload = response.json()
    assert payload["product"]["id"] == str(PRODUCT_ID)
    assert payload["notify_on"] == ["IN_STOCK", "PRICE_DOWN"]

    subscription = repository._subscriptions[(USER_ID, PRODUCT_ID)]
    assert subscription.notify_on == ["IN_STOCK", "PRICE_DOWN"]


def test__duplicate_subscription_returns_409(client: TestClient) -> None:
    repository = InMemoryFavoritesRepository()
    override_dependencies(repository=repository)

    first_response = client.post(
        f"/api/v1/favorites/{PRODUCT_ID}/subscribe",
        json={"notify_on": ["IN_STOCK"]},
    )

    second_response = client.post(
        f"/api/v1/favorites/{PRODUCT_ID}/subscribe",
        json={"notify_on": ["IN_STOCK"]},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["code"] == "SUBSCRIPTION_ALREADY_EXISTS"


@pytest.mark.parametrize(
    "body",
    [
        {"notify_on": []},
        {"notify_on": ["UNKNOWN_EVENT"]},
        {"notify_on": ["IN_STOCK", "IN_STOCK"]},
        {},
    ],
)
def test__invalid_notify_on_returns_400(client: TestClient, body: dict) -> None:
    repository = InMemoryFavoritesRepository()
    override_dependencies(repository=repository)

    response = client.post(
        f"/api/v1/favorites/{PRODUCT_ID}/subscribe",
        json=body,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_NOTIFY_ON"
    assert repository._subscriptions == {}


def test__subscribe_to_unknown_product_returns_404(client: TestClient) -> None:
    repository = InMemoryFavoritesRepository()
    product_client = StubProductClient(products={})
    override_dependencies(repository=repository, product_client=product_client)

    response = client.post(
        f"/api/v1/favorites/{UNKNOWN_PRODUCT_ID}/subscribe",
        json={"notify_on": ["IN_STOCK"]},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"
    assert repository._subscriptions == {}


def test__unsubscribe_returns_204_and_removes_subscription(client: TestClient) -> None:
    repository = InMemoryFavoritesRepository()
    override_dependencies(repository=repository)

    create_response = client.post(
        f"/api/v1/favorites/{PRODUCT_ID}/subscribe",
        json={"notify_on": ["IN_STOCK"]},
    )

    delete_response = client.delete(f"/api/v1/favorites/{PRODUCT_ID}/subscribe")

    assert create_response.status_code == 201
    assert delete_response.status_code == 204
    assert repository._subscriptions == {}


def test__unsubscribe_missing_subscription_returns_204(client: TestClient) -> None:
    repository = InMemoryFavoritesRepository()
    override_dependencies(repository=repository)

    response = client.delete(f"/api/v1/favorites/{PRODUCT_ID}/subscribe")

    assert response.status_code == 204
    assert repository._subscriptions == {}
