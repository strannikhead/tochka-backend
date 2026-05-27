from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.api.cart.dependencies import get_b2b_cart_client, get_cart_repository
from src.api.dependencies import get_optional_user_id
from src.api.events.dependencies import get_product_event_service
from src.api.products.dependencies import get_product_repository
from src.cart.b2b_client import InMemoryB2BCartClient
from src.cart.domain import B2BSkuData, CartItemStored
from src.cart.repository import InMemoryCartRepository
from src.events.repository import InMemoryEventIdempotencyRepository
from src.events.service import ProductEventService
from src.main import app
from src.orders.db_models import Base as OrdersBase
from src.orders.domain import OrderItemSnapshot, OrderSnapshot
from src.orders.repository import SqlAlchemyOrdersRepository
from src.product_card.domain import Characteristic, Image, Product, ProductStatus, Sku

TEST_USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PRODUCT_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
OTHER_PRODUCT_ID = UUID("550e8400-e29b-41d4-a716-446655440001")
SKU_ID_1 = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")
SKU_ID_2 = UUID("8a4e3f9c-1a2b-4c8d-9e5f-6b7a8c9d0e1f")
EVENT_IDEMPOTENCY_KEY = UUID("d7e8f9a0-b1c2-3456-abcd-789012345678")
ORDER_IDEMPOTENCY_KEY = UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")


@pytest.fixture(autouse=True)
def clear_overrides() -> None:
    yield
    app.dependency_overrides = {}


def _sku(
    sku_id: UUID,
    product_id: UUID,
    *,
    product_title: str,
    sku_name: str,
    stock_quantity: int = 5,
) -> B2BSkuData:
    return B2BSkuData(
        sku_id=sku_id,
        product_id=product_id,
        sku_name=sku_name,
        price=12999000,
        stock_quantity=stock_quantity,
        image_url=None,
        product_title=product_title,
        product_status="MODERATED",
        sku_code=None,
    )


def _setup_overrides(
    *,
    cart_repo: InMemoryCartRepository,
    b2b_client: InMemoryB2BCartClient,
    service: ProductEventService,
    user_id: UUID | None = None,
    product_repo=None,
) -> None:
    app.dependency_overrides[get_cart_repository] = lambda: cart_repo
    app.dependency_overrides[get_b2b_cart_client] = lambda: b2b_client
    app.dependency_overrides[get_product_event_service] = lambda: service
    app.dependency_overrides[get_optional_user_id] = lambda: user_id
    if product_repo is not None:
        app.dependency_overrides[get_product_repository] = lambda: product_repo


class StubProductRepository:
    def __init__(self, products: dict[UUID, Product]) -> None:
        self._products = products

    async def get_product(self, product_id: UUID) -> Product | None:
        return self._products.get(product_id)

    async def get_similar_products(self, product_id: UUID, limit: int) -> list[Product]:
        return []


def _build_product(product_id: UUID, *, sku_ids: list[UUID]) -> Product:
    image = Image(
        id=UUID("111e8400-e29b-41d4-a716-446655440011"),
        url="https://example.com/img.jpg",
        ordering=1,
    )
    characteristic = Characteristic(name="BRAND", value="Test")
    skus = tuple(
        Sku(
            id=sku_id,
            product_id=product_id,
            name=f"SKU {index + 1}",
            sku_code=f"TST-{index + 1}",
            price=12999000,
            discount=0,
            stock_quantity=5,
            active_quantity=5,
            characteristics=(characteristic,),
            images=(image,),
        )
        for index, sku_id in enumerate(sku_ids)
    )
    return Product(
        id=product_id,
        name="Test Product",
        slug="test-product",
        description="Test product",
        images=(image,),
        status=ProductStatus.MODERATED,
        characteristics=(characteristic,),
        skus=skus,
        min_price=12999000,
    )


def test_product_blocked_marks_cart_items_unavailable() -> None:
    cart_repo = InMemoryCartRepository()
    b2b_client = InMemoryB2BCartClient(
        skus={
            SKU_ID_1: _sku(SKU_ID_1, PRODUCT_ID, product_title="Phone", sku_name="Black"),
            SKU_ID_2: _sku(SKU_ID_2, OTHER_PRODUCT_ID, product_title="Watch", sku_name="Silver"),
        }
    )
    service = ProductEventService(cart_repo, InMemoryEventIdempotencyRepository())
    _setup_overrides(
        cart_repo=cart_repo, b2b_client=b2b_client, service=service, user_id=TEST_USER_ID
    )

    now = datetime.now(UTC)
    cart_repo._items[UUID("111e8400-e29b-41d4-a716-446655440000")] = CartItemStored(
        id=UUID("111e8400-e29b-41d4-a716-446655440000"),
        user_id=TEST_USER_ID,
        session_id=None,
        sku_id=SKU_ID_1,
        quantity=2,
        added_at=now,
        updated_at=now,
    )
    cart_repo._items[UUID("111e8400-e29b-41d4-a716-446655440001")] = CartItemStored(
        id=UUID("111e8400-e29b-41d4-a716-446655440001"),
        user_id=TEST_USER_ID,
        session_id=None,
        sku_id=SKU_ID_2,
        quantity=1,
        added_at=now,
        updated_at=now,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/events/product",
            headers={"X-Service-Key": "dev-service-key"},
            json={
                "idempotency_key": str(EVENT_IDEMPOTENCY_KEY),
                "event": "PRODUCT_BLOCKED",
                "product_id": str(PRODUCT_ID),
                "sku_ids": [str(SKU_ID_1)],
                "reason": "Описание не соответствует товару",
                "date": "2026-04-16T12:00:00Z",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"accepted": True}

        cart_response = client.get("/api/v1/cart")
        assert cart_response.status_code == 200
        cart_payload = cart_response.json()
        assert cart_payload["items_count"] == 3
        assert cart_payload["subtotal"] == 12999000
        blocked_item = next(
            item for item in cart_payload["items"] if item["sku_id"] == str(SKU_ID_1)
        )
        available_item = next(
            item for item in cart_payload["items"] if item["sku_id"] == str(SKU_ID_2)
        )
        assert blocked_item["is_available"] is False
        assert blocked_item["line_total"] == 0
        assert available_item["is_available"] is True

        validate_response = client.post("/api/v1/cart/validate")
        assert validate_response.status_code == 200
        validate_payload = validate_response.json()
        assert validate_payload["is_valid"] is False
        assert validate_payload["issues"][0]["type"] == "PRODUCT_BLOCKED"


def test_orders_not_affected_by_product_blocked(tmp_path) -> None:
    cart_repo = InMemoryCartRepository()
    b2b_client = InMemoryB2BCartClient(
        skus={
            SKU_ID_1: _sku(SKU_ID_1, PRODUCT_ID, product_title="Phone", sku_name="Black"),
        }
    )
    service = ProductEventService(cart_repo, InMemoryEventIdempotencyRepository())
    _setup_overrides(
        cart_repo=cart_repo, b2b_client=b2b_client, service=service, user_id=TEST_USER_ID
    )

    db_path = tmp_path / "orders.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare_order() -> tuple[UUID, int]:
        async with engine.begin() as conn:
            await conn.run_sync(OrdersBase.metadata.create_all)
        async with session_factory() as session:
            repo = SqlAlchemyOrdersRepository(session)
            order = OrderSnapshot.create(
                user_id=TEST_USER_ID,
                idempotency_key=ORDER_IDEMPOTENCY_KEY,
                address_id=UUID("111e8400-e29b-41d4-a716-446655440011"),
                payment_method_id=UUID("111e8400-e29b-41d4-a716-446655440012"),
                request_fingerprint="fingerprint",
                items=(
                    OrderItemSnapshot(
                        id=UUID("111e8400-e29b-41d4-a716-446655440010"),
                        sku_id=SKU_ID_1,
                        product_id=PRODUCT_ID,
                        product_title="Phone",
                        sku_name="Black",
                        quantity=1,
                        unit_price=12999000,
                        line_total=12999000,
                    ),
                ),
            )
            saved = await repo.save(order)
            return saved.id, saved.total_amount

    async def read_order(order_id: UUID) -> tuple[int, int]:
        async with session_factory() as session:
            repo = SqlAlchemyOrdersRepository(session)
            order = await repo.get_for_user(order_id=order_id, user_id=TEST_USER_ID)
            assert order is not None
            return order.total_amount, order.items[0].unit_price

    order_id, total_amount = asyncio.run(prepare_order())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/events/product",
            headers={"X-Service-Key": "dev-service-key"},
            json={
                "idempotency_key": str(EVENT_IDEMPOTENCY_KEY),
                "event": "PRODUCT_BLOCKED",
                "product_id": str(PRODUCT_ID),
                "sku_ids": [str(SKU_ID_1)],
                "reason": "Описание не соответствует товару",
                "date": "2026-04-16T12:00:00Z",
            },
        )

        assert response.status_code == 200

    persisted_total, unit_price = asyncio.run(read_order(order_id))
    assert persisted_total == total_amount == 12999000
    assert unit_price == 12999000


def test_idempotent_event_no_side_effects() -> None:
    cart_repo = InMemoryCartRepository()
    b2b_client = InMemoryB2BCartClient(
        skus={
            SKU_ID_1: _sku(SKU_ID_1, PRODUCT_ID, product_title="Phone", sku_name="Black"),
        }
    )
    service = ProductEventService(cart_repo, InMemoryEventIdempotencyRepository())
    _setup_overrides(
        cart_repo=cart_repo, b2b_client=b2b_client, service=service, user_id=TEST_USER_ID
    )

    item_id = UUID("111e8400-e29b-41d4-a716-446655440000")
    now = datetime.now(UTC)
    cart_repo._items[item_id] = CartItemStored(
        id=item_id,
        user_id=TEST_USER_ID,
        session_id=None,
        sku_id=SKU_ID_1,
        quantity=1,
        added_at=now,
        updated_at=now,
    )

    payload = {
        "idempotency_key": str(EVENT_IDEMPOTENCY_KEY),
        "event": "PRODUCT_BLOCKED",
        "product_id": str(PRODUCT_ID),
        "sku_ids": [str(SKU_ID_1)],
        "reason": "Описание не соответствует товару",
        "date": "2026-04-16T12:00:00Z",
    }

    with TestClient(app) as client:
        first_response = client.post(
            "/api/v1/events/product", headers={"X-Service-Key": "dev-service-key"}, json=payload
        )
        first_item = cart_repo._items[item_id]
        second_response = client.post(
            "/api/v1/events/product", headers={"X-Service-Key": "dev-service-key"}, json=payload
        )
        second_item = cart_repo._items[item_id]

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert first_item.unavailable_reason == "PRODUCT_BLOCKED"
        assert second_item.unavailable_reason == "PRODUCT_BLOCKED"
        assert first_item.updated_at == second_item.updated_at


def test_missing_service_key_returns_401() -> None:
    cart_repo = InMemoryCartRepository()
    b2b_client = InMemoryB2BCartClient(
        skus={SKU_ID_1: _sku(SKU_ID_1, PRODUCT_ID, product_title="Phone", sku_name="Black")}
    )
    service = ProductEventService(cart_repo, InMemoryEventIdempotencyRepository())
    _setup_overrides(
        cart_repo=cart_repo, b2b_client=b2b_client, service=service, user_id=TEST_USER_ID
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/events/product",
            json={
                "idempotency_key": str(EVENT_IDEMPOTENCY_KEY),
                "event": "PRODUCT_BLOCKED",
                "product_id": str(PRODUCT_ID),
                "sku_ids": [str(SKU_ID_1)],
                "reason": "Описание не соответствует товару",
                "date": "2026-04-16T12:00:00Z",
            },
        )

        assert response.status_code == 401
        assert response.json() == {"code": "UNAUTHORIZED", "message": "Требуется сервисный ключ"}


def test_b2b_event_route_returns_202_and_409() -> None:
    cart_repo = InMemoryCartRepository()
    b2b_client = InMemoryB2BCartClient(
        skus={
            SKU_ID_1: _sku(SKU_ID_1, PRODUCT_ID, product_title="Phone", sku_name="Black"),
        }
    )
    service = ProductEventService(cart_repo, InMemoryEventIdempotencyRepository())
    product_repo = StubProductRepository(
        {PRODUCT_ID: _build_product(PRODUCT_ID, sku_ids=[SKU_ID_1])}
    )
    _setup_overrides(
        cart_repo=cart_repo,
        b2b_client=b2b_client,
        service=service,
        user_id=TEST_USER_ID,
        product_repo=product_repo,
    )

    payload = {
        "event_type": "PRODUCT_BLOCKED",
        "idempotency_key": str(EVENT_IDEMPOTENCY_KEY),
        "occurred_at": "2026-04-16T12:00:00Z",
        "payload": {"product_id": str(PRODUCT_ID), "reason": "Описание не соответствует товару"},
    }

    with TestClient(app) as client:
        first_response = client.post(
            "/api/v1/b2b/events", headers={"X-Service-Key": "dev-service-key"}, json=payload
        )
        second_response = client.post(
            "/api/v1/b2b/events", headers={"X-Service-Key": "dev-service-key"}, json=payload
        )

        assert first_response.status_code == 202
        assert first_response.json() == {"accepted": True}
        assert second_response.status_code == 409
        assert second_response.json() == {"accepted": False}


def test_b2b_event_route_missing_service_key_returns_401() -> None:
    cart_repo = InMemoryCartRepository()
    b2b_client = InMemoryB2BCartClient(
        skus={SKU_ID_1: _sku(SKU_ID_1, PRODUCT_ID, product_title="Phone", sku_name="Black")}
    )
    service = ProductEventService(cart_repo, InMemoryEventIdempotencyRepository())
    product_repo = StubProductRepository(
        {PRODUCT_ID: _build_product(PRODUCT_ID, sku_ids=[SKU_ID_1])}
    )
    _setup_overrides(
        cart_repo=cart_repo,
        b2b_client=b2b_client,
        service=service,
        user_id=TEST_USER_ID,
        product_repo=product_repo,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/b2b/events",
            json={
                "event_type": "PRODUCT_BLOCKED",
                "idempotency_key": str(EVENT_IDEMPOTENCY_KEY),
                "occurred_at": "2026-04-16T12:00:00Z",
                "payload": {
                    "product_id": str(PRODUCT_ID),
                    "reason": "Описание не соответствует товару",
                },
            },
        )

        assert response.status_code == 401
        assert response.json() == {"code": "UNAUTHORIZED", "message": "Требуется сервисный ключ"}
