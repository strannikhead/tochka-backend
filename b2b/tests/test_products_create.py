"""Canonical create-product flow for US-B2B-01 (POST /api/v1/products).

Behaviour follows b2b/openapi.yaml:
  * required body fields = title, description, category_id;
  * images / characteristics are optional (default []);
  * validation failures return 422 (ValidationError -> Error schema).

seller_id is taken from the JWT only, never from the request body (IDOR guard).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from b2b.src.auth import (
    JWT_ALGORITHM,
    JWT_SECRET,
    get_current_seller_id,
)
from b2b.src.main import app
from b2b.src.models import Product, ProductStatus
from b2b.src.products.dependencies import get_products_service
from b2b.src.products.domain.errors import CategoryNotFoundError
from b2b.src.products.domain.models import CreateProductCommand

JWT_SELLER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
KNOWN_CATEGORY_ID = "550e8400-e29b-41d4-a716-446655440010"
UNKNOWN_CATEGORY_ID = "11111111-1111-1111-1111-111111111111"


class StubProductsService:
    """Mimics ProductsService.create_product without touching the DB."""

    def __init__(self, *, known_categories: set[str]) -> None:
        self._known_categories = known_categories
        self.received_command: CreateProductCommand | None = None

    async def create_product(self, command: CreateProductCommand) -> Product:
        self.received_command = command
        if str(command.category_id) not in self._known_categories:
            raise CategoryNotFoundError("Категория не найдена")
        now = datetime.now(UTC)
        return Product(
            id=uuid4(),
            seller_id=command.seller_id,
            title=command.title,
            slug=command.slug,
            description=command.description,
            category_id=command.category_id,
            status=ProductStatus.CREATED,
            images=[{"url": i.url, "ordering": i.ordering} for i in command.images],
            characteristics=[{"name": c.name, "value": c.value} for c in command.characteristics],
            created_at=now,
            updated_at=now,
        )


@pytest.fixture()
def service() -> StubProductsService:
    return StubProductsService(known_categories={KNOWN_CATEGORY_ID})


@pytest.fixture()
def client(service: StubProductsService) -> Generator[TestClient]:
    app.dependency_overrides = {}
    app.dependency_overrides[get_products_service] = lambda: service
    # Stand in for the JWT-derived seller; real decoding lives in b2b.src.auth.
    app.dependency_overrides[get_current_seller_id] = lambda: JWT_SELLER_ID
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


def _valid_body() -> dict[str, object]:
    return {
        "title": "iPhone 15 Pro Max",
        "description": "Флагман Apple",
        "category_id": KNOWN_CATEGORY_ID,
        "images": [{"url": "https://example.com/a.jpg", "ordering": 0}],
        "characteristics": [{"name": "Бренд", "value": "Apple"}],
    }


def test_create_product_returns_201_with_created_status(client: TestClient) -> None:
    response = client.post("/api/v1/products", json=_valid_body())

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "CREATED"
    assert payload["skus"] == []
    assert payload["deleted"] is False
    assert payload["title"] == "iPhone 15 Pro Max"


def test_seller_id_taken_from_jwt(client: TestClient, service: StubProductsService) -> None:
    body = _valid_body()
    # A hostile client tries to spoof another seller via the body.
    body["seller_id"] = "99999999-9999-9999-9999-999999999999"

    response = client.post("/api/v1/products", json=body)

    assert response.status_code == 201
    assert response.json()["seller_id"] == str(JWT_SELLER_ID)
    # The command the service received carries the JWT seller, not the body one.
    assert service.received_command is not None
    assert service.received_command.seller_id == JWT_SELLER_ID


def test_missing_images_is_allowed(client: TestClient) -> None:
    # Per OpenAPI, images is optional and defaults to []. This must NOT 400/422.
    body = _valid_body()
    del body["images"]

    response = client.post("/api/v1/products", json=body)

    assert response.status_code == 201
    assert response.json()["images"] == []


def test_missing_category_returns_422(client: TestClient) -> None:
    body = _valid_body()
    del body["category_id"]

    response = client.post("/api/v1/products", json=body)

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert "category_id" in payload["message"]


def test_invalid_category_id_returns_422(client: TestClient) -> None:
    body = _valid_body()
    body["category_id"] = UNKNOWN_CATEGORY_ID

    response = client.post("/api/v1/products", json=body)

    assert response.status_code == 422
    assert response.json()["details"]["field"] == "category_id"


def test_missing_title_returns_422(client: TestClient) -> None:
    body = _valid_body()
    del body["title"]

    response = client.post("/api/v1/products", json=body)

    assert response.status_code == 422
    assert "title" in response.json()["message"]


# --- Authentication (real get_current_seller_id, no override) ---


@pytest.fixture()
def auth_client(service: StubProductsService) -> Generator[TestClient]:
    # Only the service is stubbed; the real JWT dependency runs so auth is exercised.
    app.dependency_overrides = {}
    app.dependency_overrides[get_products_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


def test_missing_bearer_returns_401_error_schema(auth_client: TestClient) -> None:
    response = auth_client.post("/api/v1/products", json=_valid_body())

    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "UNAUTHORIZED"
    assert payload["message"]


def test_invalid_bearer_returns_401_error_schema(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/v1/products",
        json=_valid_body(),
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "UNAUTHORIZED"
    assert payload["message"]


def test_valid_jwt_seller_id_drives_creation(auth_client: TestClient) -> None:
    # A real token: seller_id is decoded from claims and lands on the created product.
    token = jwt.encode({"sub": str(JWT_SELLER_ID)}, JWT_SECRET, algorithm=JWT_ALGORITHM)

    response = auth_client.post(
        "/api/v1/products",
        json=_valid_body(),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["seller_id"] == str(JWT_SELLER_ID)
