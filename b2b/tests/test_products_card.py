"""Canonical view-product flow for US-B2B-05 (GET /api/v1/products/{id}).

Behaviour follows b2b/openapi.yaml:
  * seller (JWT) gets ProductResponse incl. cost_price / reserved_quantity;
  * BLOCKED product exposes blocking_reason_id + moderator_comment (the spec card
    does NOT carry a blocking_reason object or field_reports);
  * someone else's product and a missing id both return 404 (never 403), so the
    existence of another seller's product is not disclosed.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from b2b.src.auth import get_optional_seller_id
from b2b.src.main import app
from b2b.src.models import SKU, Product, ProductStatus
from b2b.src.products.dependencies import get_products_service
from b2b.src.products.domain.errors import ProductNotFoundError

SELLER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
OTHER_SELLER_ID = UUID("550e8400-e29b-41d4-a716-4466554400ff")
BLOCKING_REASON_ID = UUID("660e8400-e29b-41d4-a716-446655440010")


def _make_sku(product_id: UUID) -> SKU:
    now = datetime.now(UTC)
    return SKU(
        id=uuid4(),
        product_id=product_id,
        name="256GB Black",
        price=12999000,
        discount=0,
        cost_price=9990000,
        stock_quantity=12,
        active_quantity=10,
        reserved_quantity=2,
        article="IP15PM-BLK-256",
        images=[{"id": str(uuid4()), "url": "/s3/a.jpg", "ordering": 0}],
        characteristics=[{"id": str(uuid4()), "name": "Цвет", "value": "Чёрный"}],
        created_at=now,
        updated_at=now,
    )


def _make_product(*, status: ProductStatus, seller_id: UUID = SELLER_ID) -> Product:
    now = datetime.now(UTC)
    product_id = uuid4()
    blocked = status == ProductStatus.BLOCKED
    product = Product(
        id=product_id,
        seller_id=seller_id,
        title="iPhone 15 Pro Max",
        slug="iphone-15-pro-max",
        description="Флагман Apple",
        status=status,
        category_id=UUID("550e8400-e29b-41d4-a716-446655440010"),
        images=[{"id": str(uuid4()), "url": "/s3/cover.jpg", "ordering": 0}],
        characteristics=[{"id": str(uuid4()), "name": "Бренд", "value": "Apple"}],
        blocking_reason_id=BLOCKING_REASON_ID if blocked else None,
        moderator_comment="Некорректное название" if blocked else None,
        created_at=now,
        updated_at=now,
    )
    product.skus = [_make_sku(product_id)]
    return product


class StubProductsService:
    def __init__(self, product: Product | None) -> None:
        self._product = product

    async def get_product_for_seller(self, product_id: UUID, seller_id: UUID) -> Product:
        if (
            self._product is None
            or self._product.id != product_id
            or self._product.seller_id != seller_id
        ):
            raise ProductNotFoundError("Товар не найден")
        return self._product

    async def get_product_for_service(self, product_id: UUID) -> Product:
        if self._product is None or self._product.id != product_id:
            raise ProductNotFoundError("Товар не найден")
        return self._product


def _client(product: Product | None, *, seller_id: UUID | None = SELLER_ID) -> TestClient:
    app.dependency_overrides = {}
    app.dependency_overrides[get_products_service] = lambda: StubProductsService(product)
    app.dependency_overrides[get_optional_seller_id] = lambda: seller_id
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides() -> Generator[None]:
    yield
    app.dependency_overrides = {}


def test_get_moderated_product_returns_full_payload() -> None:
    product = _make_product(status=ProductStatus.MODERATED)
    client = _client(product)

    response = client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(product.id)
    assert payload["status"] == "MODERATED"
    assert payload["blocking_reason_id"] is None
    # Seller view carries the sensitive economics on each SKU.
    sku = payload["skus"][0]
    assert sku["cost_price"] == 9990000
    assert sku["reserved_quantity"] == 2
    # Nested objects must satisfy their *Response schemas (id is required).
    assert payload["images"][0].keys() >= {"id", "url", "ordering"}
    assert payload["characteristics"][0].keys() >= {"id", "name", "value"}
    assert sku["images"][0].keys() >= {"id", "url", "ordering"}


def test_get_blocked_product_returns_blocking_reason_and_field_reports() -> None:
    product = _make_product(status=ProductStatus.BLOCKED)
    client = _client(product)

    response = client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "BLOCKED"
    # Per OpenAPI the card carries blocking_reason_id + moderator_comment (no nested
    # blocking_reason object, no field_reports array — those live on moderation events).
    assert payload["blocking_reason_id"] == str(BLOCKING_REASON_ID)
    assert payload["moderator_comment"] == "Некорректное название"


def test_get_others_product_returns_404() -> None:
    # Product belongs to another seller; the authenticated seller must get 404, not 403.
    product = _make_product(status=ProductStatus.MODERATED, seller_id=OTHER_SELLER_ID)
    client = _client(product, seller_id=SELLER_ID)

    response = client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 404


def test_get_nonexistent_returns_404() -> None:
    client = _client(None)

    response = client.get(f"/api/v1/products/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_slug_is_always_a_string_when_absent() -> None:
    # *Response schemas require slug as a non-null string even if none was set.
    product = _make_product(status=ProductStatus.MODERATED)
    product.slug = None
    client = _client(product)

    response = client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 200
    assert isinstance(response.json()["slug"], str)


def test_service_key_returns_public_payload_without_sensitive_fields() -> None:
    # X-Service-Key (B2C catalog) must never see cost_price / reserved_quantity.
    product = _make_product(status=ProductStatus.MODERATED)
    client = _client(product, seller_id=None)

    response = client.get(
        f"/api/v1/products/{product.id}",
        headers={"X-Service-Key": "dev-service-key"},
    )

    assert response.status_code == 200
    sku = response.json()["skus"][0]
    assert "cost_price" not in sku
    assert "reserved_quantity" not in sku


def test_unauthenticated_returns_401_with_error_shape() -> None:
    # No Bearer and no X-Service-Key: the seller card requires auth. The response must
    # follow the OpenAPI Error schema {code, message}, not FastAPI's default {detail}.
    product = _make_product(status=ProductStatus.MODERATED)
    # Only the service is stubbed; the real get_optional_seller_id runs and yields None.
    app.dependency_overrides = {}
    app.dependency_overrides[get_products_service] = lambda: StubProductsService(product)
    client = TestClient(app)

    response = client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 401
    body = response.json()
    assert set(body.keys()) == {"code", "message"}
    assert body["code"] == "UNAUTHORIZED"
    assert isinstance(body["message"], str) and body["message"]
