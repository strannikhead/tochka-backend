"""Canonical delete-product flow for US-B2B-04 (DELETE /api/v1/products/{id}).

Behaviour follows b2b/openapi.yaml:
  * soft delete — `deleted=true`, the row and its moderation status are kept;
  * two cascade events go through the outbox: DELETED (Moderation) and
    PRODUCT_DELETED (B2C, carrying sku_ids so B2C can flag cart lines);
  * re-deleting an already-deleted product is a 404 (no active product) — the spec's
    DELETE responses are 204/403/404, there is no 400;
  * another seller's product → 403.

Integration style (real async engine) mirrors test_products_edit.py and needs the
`aiosqlite` dev dependency.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from b2b.src.auth import get_current_seller_id
from b2b.src.db import SessionLocal
from b2b.src.main import app
from b2b.src.models import SKU, Base, Category, OutboxEvent, Product, ProductStatus

SELLER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
OTHER_SELLER_ID = UUID("550e8400-e29b-41d4-a716-4466554400ff")
CATEGORY_ID = UUID("550e8400-e29b-41d4-a716-446655440010")


class DbState:
    def __init__(self, engine, session_factory, products: dict[str, UUID], skus: dict[str, UUID]):
        self.engine = engine
        self.session_factory = session_factory
        self.products = products
        self.skus = skus


def _active_sku(product_id: UUID, *, name: str, article: str) -> SKU:
    now = datetime.now(UTC)
    return SKU(
        id=uuid4(),
        product_id=product_id,
        name=name,
        price=12999000,
        discount=0,
        cost_price=9990000,
        stock_quantity=12,
        active_quantity=10,
        reserved_quantity=2,
        article=article,
        images=[],
        characteristics=[],
        created_at=now,
        updated_at=now,
    )


def _product(*, seller_id: UUID, title: str, slug: str, deleted: bool = False) -> Product:
    now = datetime.now(UTC)
    product = Product(
        id=uuid4(),
        seller_id=seller_id,
        title=title,
        slug=slug,
        description="desc",
        status=ProductStatus.MODERATED,
        category_id=CATEGORY_ID,
        images=[],
        characteristics=[],
        deleted=deleted,
        created_at=now,
        updated_at=now,
    )
    product.skus = [_active_sku(product.id, name=f"{slug}-sku", article=slug.upper())]
    return product


@pytest.fixture()
def db_state(tmp_path: Path) -> Generator[DbState]:
    db_path = tmp_path / "b2b.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> dict[str, dict[str, UUID]]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        now = datetime.now(UTC)
        products: dict[str, UUID] = {}
        skus: dict[str, UUID] = {}
        async with session_factory() as session:
            session.add(
                Category(
                    id=CATEGORY_ID,
                    name="Phones",
                    parent_id=None,
                    level=0,
                    path="/phones",
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            active = _product(seller_id=SELLER_ID, title="Active", slug="active-product")
            predeleted = _product(
                seller_id=SELLER_ID, title="Gone", slug="gone-product", deleted=True
            )
            other = _product(seller_id=OTHER_SELLER_ID, title="Other", slug="other-product")
            session.add_all([active, predeleted, other])
            await session.commit()

            for key, product in (("active", active), ("deleted", predeleted), ("other", other)):
                products[key] = product.id
                skus[key] = product.skus[0].id

        return {"products": products, "skus": skus}

    payload = asyncio.run(prepare())
    state = DbState(engine, session_factory, payload["products"], payload["skus"])

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


async def _fetch_outbox(session_factory) -> list[OutboxEvent]:
    async with session_factory() as session:
        result = await session.execute(select(OutboxEvent).order_by(OutboxEvent.created_at.asc()))
        return list(result.scalars().all())


def test_delete_sets_deleted_true(client: TestClient, db_state: DbState) -> None:
    product_id = db_state.products["active"]

    response = client.delete(f"/api/v1/products/{product_id}")

    assert response.status_code == 204
    product = asyncio.run(_fetch_product(db_state.session_factory, product_id))
    assert product is not None
    assert product.deleted is True
    # Soft delete keeps the moderation status intact (no DELETED status value).
    assert product.status == ProductStatus.MODERATED


def test_delete_emits_event_to_moderation(client: TestClient, db_state: DbState) -> None:
    product_id = db_state.products["active"]

    client.delete(f"/api/v1/products/{product_id}")

    events = asyncio.run(_fetch_outbox(db_state.session_factory))
    moderation = [e for e in events if e.event_type == "DELETED"]
    assert len(moderation) == 1
    assert moderation[0].payload["product_id"] == str(product_id)


def test_delete_emits_product_deleted_to_b2c(client: TestClient, db_state: DbState) -> None:
    product_id = db_state.products["active"]
    sku_id = db_state.skus["active"]

    client.delete(f"/api/v1/products/{product_id}")

    events = asyncio.run(_fetch_outbox(db_state.session_factory))
    b2c = [e for e in events if e.event_type == "PRODUCT_DELETED"]
    assert len(b2c) == 1
    assert b2c[0].payload["product_id"] == str(product_id)
    assert b2c[0].payload["sku_ids"] == [str(sku_id)]


def test_delete_already_deleted_returns_404(client: TestClient, db_state: DbState) -> None:
    # Re-deleting an already soft-deleted product: spec DELETE has no 400, so 404.
    already_deleted_id = db_state.products["deleted"]

    response = client.delete(f"/api/v1/products/{already_deleted_id}")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_delete_others_product_returns_403(client: TestClient, db_state: DbState) -> None:
    other_product_id = db_state.products["other"]

    response = client.delete(f"/api/v1/products/{other_product_id}")

    assert response.status_code == 403
    assert response.json()["code"] == "NOT_OWNER"


def test_deleted_product_not_in_seller_list(client: TestClient, db_state: DbState) -> None:
    product_id = db_state.products["active"]
    client.delete(f"/api/v1/products/{product_id}")

    response = client.get("/api/v1/products")

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert str(product_id) not in ids
