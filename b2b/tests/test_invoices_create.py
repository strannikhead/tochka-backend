"""Canonical create-invoice flow for US-B2B-06 (POST /api/v1/invoices).

Behaviour follows b2b/openapi.yaml:
  * auth via JWT (seller), success -> 201 InvoiceResponse, new invoice status = CREATED;
  * items must reference the seller's own SKUs whose product is MODERATED.

Business rules (the spec does not document error codes for this endpoint, so they
follow the canon): empty items -> 400, non-MODERATED SKU -> 400, other seller's SKU -> 403.

Integration style (real async engine) mirrors test_products_edit.py; needs `aiosqlite`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from b2b.src.auth import get_current_seller_id
from b2b.src.db import SessionLocal
from b2b.src.main import app
from b2b.src.models import SKU, Base, Category, Product, ProductStatus

SELLER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
OTHER_SELLER_ID = UUID("550e8400-e29b-41d4-a716-4466554400ff")
CATEGORY_ID = UUID("550e8400-e29b-41d4-a716-446655440010")


class DbState:
    def __init__(self, engine, session_factory, skus: dict[str, UUID]):
        self.engine = engine
        self.session_factory = session_factory
        self.skus = skus


def _product_with_sku(*, seller_id: UUID, status: ProductStatus, slug: str) -> Product:
    now = datetime.now(UTC)
    product = Product(
        id=uuid4(),
        seller_id=seller_id,
        title=slug,
        slug=slug,
        description="desc",
        status=status,
        category_id=CATEGORY_ID,
        images=[],
        characteristics=[],
        created_at=now,
        updated_at=now,
    )
    product.skus = [
        SKU(
            id=uuid4(),
            product_id=product.id,
            name=f"{slug}-sku",
            price=12999000,
            discount=0,
            cost_price=9990000,
            stock_quantity=0,
            active_quantity=0,
            reserved_quantity=0,
            article=slug.upper(),
            images=[],
            characteristics=[],
            created_at=now,
            updated_at=now,
        )
    ]
    return product


@pytest.fixture()
def db_state(tmp_path: Path) -> Generator[DbState]:
    db_path = tmp_path / "b2b.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> dict[str, UUID]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        now = datetime.now(UTC)
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
            moderated = _product_with_sku(
                seller_id=SELLER_ID, status=ProductStatus.MODERATED, slug="moderated"
            )
            created = _product_with_sku(
                seller_id=SELLER_ID, status=ProductStatus.CREATED, slug="created"
            )
            other = _product_with_sku(
                seller_id=OTHER_SELLER_ID, status=ProductStatus.MODERATED, slug="other"
            )
            session.add_all([moderated, created, other])
            await session.commit()
            skus = {
                "moderated": moderated.skus[0].id,
                "non_moderated": created.skus[0].id,
                "other": other.skus[0].id,
            }
        return skus

    skus = asyncio.run(prepare())
    state = DbState(engine, session_factory, skus)

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


def test_create_invoice_with_moderated_sku_returns_201(
    client: TestClient, db_state: DbState
) -> None:
    response = client.post(
        "/api/v1/invoices",
        json={"items": [{"sku_id": str(db_state.skus["moderated"]), "quantity": 5}]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "CREATED"
    assert payload["seller_id"] == str(SELLER_ID)
    assert len(payload["items"]) == 1
    assert payload["items"][0]["sku_id"] == str(db_state.skus["moderated"])
    assert payload["items"][0]["quantity"] == 5
    assert payload["items"][0]["accepted_quantity"] == 0


def test_empty_items_returns_400(client: TestClient) -> None:
    response = client.post("/api/v1/invoices", json={"items": []})

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_non_moderated_sku_returns_400(client: TestClient, db_state: DbState) -> None:
    response = client.post(
        "/api/v1/invoices",
        json={"items": [{"sku_id": str(db_state.skus["non_moderated"]), "quantity": 1}]},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_others_sku_returns_403(client: TestClient, db_state: DbState) -> None:
    response = client.post(
        "/api/v1/invoices",
        json={"items": [{"sku_id": str(db_state.skus["other"]), "quantity": 1}]},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "NOT_OWNER"
