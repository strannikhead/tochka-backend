from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from b2b.src.auth import get_current_seller_id
from b2b.src.db import SessionLocal
from b2b.src.main import app
from b2b.src.models import (
    SKU,
    Base,
    Category,
    OutboxEvent,
    Product,
    ProductStatus,
)

SELLER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
OTHER_SELLER_ID = UUID("550e8400-e29b-41d4-a716-4466554400ff")
CATEGORY_ID = UUID("550e8400-e29b-41d4-a716-446655440010")
OTHER_CATEGORY_ID = UUID("550e8400-e29b-41d4-a716-446655440011")


class DbState:
    def __init__(
        self,
        engine,
        session_factory,
        products: dict[str, UUID],
        skus: dict[str, UUID],
    ) -> None:
        self.engine = engine
        self.session_factory = session_factory
        self.products = products
        self.skus = skus


@pytest.fixture()
def db_state(tmp_path: Path) -> Generator[DbState]:
    db_path = tmp_path / "b2b.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> dict[str, dict[str, UUID]]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        now = datetime.now(UTC)
        product_ids: dict[str, UUID] = {}
        sku_ids: dict[str, UUID] = {}

        async with session_factory() as session:
            await session.execute(delete(OutboxEvent))
            await session.execute(delete(SKU))
            await session.execute(delete(Product))
            await session.execute(delete(Category))

            session.add_all(
                [
                    Category(
                        id=CATEGORY_ID,
                        name="Phones",
                        parent_id=None,
                        level=0,
                        path="/phones",
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    ),
                    Category(
                        id=OTHER_CATEGORY_ID,
                        name="Accessories",
                        parent_id=None,
                        level=0,
                        path="/accessories",
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            )

            moderated_product = Product(
                id=uuid4(),
                seller_id=SELLER_ID,
                title="iPhone 15 Pro Max",
                slug="iphone-15-pro-max",
                description="Original description",
                status=ProductStatus.MODERATED,
                category_id=CATEGORY_ID,
                images=[{"id": str(uuid4()), "url": "/s3/cover.jpg", "ordering": 0}],
                characteristics=[{"id": str(uuid4()), "name": "Бренд", "value": "Apple"}],
                created_at=now,
                updated_at=now,
            )
            moderated_product.skus = [
                SKU(
                    id=uuid4(),
                    product_id=moderated_product.id,
                    name="256GB Black",
                    price=12999000,
                    discount=0,
                    cost_price=9990000,
                    stock_quantity=12,
                    active_quantity=10,
                    reserved_quantity=2,
                    article="IP15PM-BLK-256",
                    images=[],
                    characteristics=[{"id": str(uuid4()), "name": "Цвет", "value": "Чёрный"}],
                    created_at=now,
                    updated_at=now,
                )
            ]
            product_ids["moderated"] = moderated_product.id
            sku_ids["moderated"] = moderated_product.skus[0].id

            blocked_product = Product(
                id=uuid4(),
                seller_id=SELLER_ID,
                title="Blocked product",
                slug="blocked-product",
                description="Needs fixing",
                status=ProductStatus.BLOCKED,
                category_id=CATEGORY_ID,
                images=[],
                characteristics=[],
                blocking_reason_id=UUID("660e8400-e29b-41d4-a716-446655440010"),
                moderator_comment="Wrong title",
                created_at=now,
                updated_at=now,
            )
            blocked_product.skus = [
                SKU(
                    id=uuid4(),
                    product_id=blocked_product.id,
                    name="Blocked SKU",
                    price=999000,
                    discount=0,
                    cost_price=450000,
                    stock_quantity=5,
                    active_quantity=4,
                    reserved_quantity=0,
                    article="BLK-001",
                    images=[],
                    characteristics=[],
                    created_at=now,
                    updated_at=now,
                )
            ]
            product_ids["blocked"] = blocked_product.id
            sku_ids["blocked"] = blocked_product.skus[0].id

            hard_blocked_product = Product(
                id=uuid4(),
                seller_id=SELLER_ID,
                title="Hard blocked product",
                slug="hard-blocked-product",
                description="Forbidden to edit",
                status=ProductStatus.HARD_BLOCKED,
                category_id=CATEGORY_ID,
                images=[],
                characteristics=[],
                blocking_reason_id=UUID("660e8400-e29b-41d4-a716-446655440011"),
                moderator_comment="Severe violation",
                created_at=now,
                updated_at=now,
            )
            hard_blocked_product.skus = [
                SKU(
                    id=uuid4(),
                    product_id=hard_blocked_product.id,
                    name="Hard blocked SKU",
                    price=199000,
                    discount=0,
                    cost_price=120000,
                    stock_quantity=2,
                    active_quantity=2,
                    reserved_quantity=0,
                    article="HARD-001",
                    images=[],
                    characteristics=[],
                    created_at=now,
                    updated_at=now,
                )
            ]
            product_ids["hard_blocked"] = hard_blocked_product.id
            sku_ids["hard_blocked"] = hard_blocked_product.skus[0].id

            other_seller_product = Product(
                id=uuid4(),
                seller_id=OTHER_SELLER_ID,
                title="Other seller product",
                slug="other-seller-product",
                description="Belongs to someone else",
                status=ProductStatus.MODERATED,
                category_id=CATEGORY_ID,
                images=[],
                characteristics=[],
                created_at=now,
                updated_at=now,
            )
            other_seller_product.skus = [
                SKU(
                    id=uuid4(),
                    product_id=other_seller_product.id,
                    name="Other seller SKU",
                    price=500000,
                    discount=0,
                    cost_price=300000,
                    stock_quantity=1,
                    active_quantity=1,
                    reserved_quantity=0,
                    article="OTHER-001",
                    images=[],
                    characteristics=[],
                    created_at=now,
                    updated_at=now,
                )
            ]
            product_ids["other"] = other_seller_product.id
            sku_ids["other"] = other_seller_product.skus[0].id

            session.add_all(
                [moderated_product, blocked_product, hard_blocked_product, other_seller_product]
            )
            await session.commit()

        return {"products": product_ids, "skus": sku_ids}

    payload = asyncio.run(prepare())
    state = DbState(
        engine=engine,
        session_factory=session_factory,
        products=payload["products"],
        skus=payload["skus"],
    )

    import b2b.src.db as db_module

    original_session_local = SessionLocal
    db_module.SessionLocal = session_factory
    app.dependency_overrides = {}
    app.dependency_overrides[get_current_seller_id] = lambda: SELLER_ID

    try:
        yield state
    finally:
        app.dependency_overrides = {}
        db_module.SessionLocal = original_session_local
        asyncio.run(engine.dispose())


@pytest.fixture()
def client(db_state: DbState) -> Generator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


async def _fetch_product(session_factory, product_id: UUID) -> Product | None:
    async with session_factory() as session:
        return await session.get(Product, product_id)


async def _fetch_sku(session_factory, sku_id: UUID) -> SKU | None:
    async with session_factory() as session:
        return await session.get(SKU, sku_id)


async def _fetch_outbox(session_factory) -> list[OutboxEvent]:
    async with session_factory() as session:
        result = await session.execute(select(OutboxEvent).order_by(OutboxEvent.created_at.asc()))
        return list(result.scalars().all())


def test_edit_moderated_product_returns_to_on_moderation(
    client: TestClient,
    db_state: DbState,
) -> None:
    product_id = db_state.products["moderated"]

    response = client.put(
        f"/api/v1/products/{product_id}",
        json={
            "title": "iPhone 15 Pro Max updated",
            "description": "Updated description",
            "category_id": str(CATEGORY_ID),
            "characteristics": [{"name": "Бренд", "value": "Apple"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ON_MODERATION"
    assert payload["title"] == "iPhone 15 Pro Max updated"
    assert payload["blocking_reason_id"] is None
    assert payload["moderator_comment"] is None

    product = asyncio.run(_fetch_product(db_state.session_factory, product_id))
    assert product is not None
    assert product.status == ProductStatus.ON_MODERATION

    outbox_events = asyncio.run(_fetch_outbox(db_state.session_factory))
    assert len(outbox_events) == 1
    assert outbox_events[0].event_type == "EDITED"
    assert outbox_events[0].payload["event"] == "EDITED"
    assert outbox_events[0].payload["product_id"] == str(product_id)


def test_edit_blocked_product_returns_to_on_moderation(
    client: TestClient,
    db_state: DbState,
) -> None:
    product_id = db_state.products["blocked"]

    response = client.put(
        f"/api/v1/products/{product_id}",
        json={
            "description": "Reworked description",
            "category_id": str(CATEGORY_ID),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ON_MODERATION"
    assert payload["blocking_reason_id"] is None
    assert payload["moderator_comment"] is None

    product = asyncio.run(_fetch_product(db_state.session_factory, product_id))
    assert product is not None
    assert product.status == ProductStatus.ON_MODERATION

    outbox_events = asyncio.run(_fetch_outbox(db_state.session_factory))
    assert len(outbox_events) == 1
    assert outbox_events[0].payload["product_id"] == str(product_id)


def test_reserves_preserved_after_sku_edit(client: TestClient, db_state: DbState) -> None:
    sku_id = db_state.skus["moderated"]
    product_id = db_state.products["moderated"]

    response = client.put(
        f"/api/v1/skus/{sku_id}",
        json={
            "name": "256GB Black Titanium",
            "price": 13499000,
            "discount": 500000,
            "cost_price": 9800000,
            "article": "IP15PM-BLK-256-TI",
            "characteristics": [{"name": "Цвет", "value": "Чёрный титан"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reserved_quantity"] == 2
    assert payload["name"] == "256GB Black Titanium"
    assert payload["cost_price"] == 9800000

    sku = asyncio.run(_fetch_sku(db_state.session_factory, sku_id))
    assert sku is not None
    assert sku.reserved_quantity == 2

    product = asyncio.run(_fetch_product(db_state.session_factory, product_id))
    assert product is not None
    assert product.status == ProductStatus.ON_MODERATION

    outbox_events = asyncio.run(_fetch_outbox(db_state.session_factory))
    assert len(outbox_events) == 1
    assert outbox_events[0].payload["product_id"] == str(product_id)


@pytest.mark.parametrize(
    ("endpoint", "entity_id"),
    [
        ("products", "hard_blocked"),
        ("skus", "hard_blocked"),
    ],
)
def test_edit_hard_blocked_returns_403(
    client: TestClient,
    db_state: DbState,
    endpoint: str,
    entity_id: str,
) -> None:
    hard_blocked_product_id = db_state.products[entity_id]
    hard_blocked_sku_id = db_state.skus[entity_id]
    target_id = hard_blocked_product_id if endpoint == "products" else hard_blocked_sku_id
    body = {
        "title": "Nope",
        "description": "Still nope",
        "category_id": str(CATEGORY_ID),
        "name": "Nope",
        "price": 1,
    }

    response = client.put(f"/api/v1/{endpoint}/{target_id}", json=body)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.parametrize(
    ("endpoint", "entity_id"),
    [
        ("products", "other"),
        ("skus", "other"),
    ],
)
def test_edit_others_product_returns_403(
    client: TestClient,
    db_state: DbState,
    endpoint: str,
    entity_id: str,
) -> None:
    target_id = db_state.products[entity_id] if endpoint == "products" else db_state.skus[entity_id]
    body = {
        "title": "Unauthorized edit",
        "description": "Unauthorized edit",
        "category_id": str(CATEGORY_ID),
        "name": "Unauthorized edit",
        "price": 1,
    }

    response = client.put(f"/api/v1/{endpoint}/{target_id}", json=body)

    assert response.status_code == 403
    assert response.json()["code"] == "NOT_OWNER"
