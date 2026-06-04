"""US-B2B-11: GET /api/v1/products — seller cabinet list.

Canonical scenarios:
  happy:   list_returns_only_own_products, deleted_products_visible_with_deleted_flag
  unhappy: idor_query_param_seller_id_ignored, status_filter_works_correctly
  extra:   search_by_title_case_insensitive

Integration tests against SQLite (same pattern as test_products_delete.py).
seller_id is taken from the JWT only — never from the query string (IDOR guard).
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

import b2b.src.db as db_module
from b2b.src.auth import get_current_seller_id
from b2b.src.main import app
from b2b.src.models import SKU, Base, Category, Product, ProductStatus

SELLER_ID = UUID("aa000000-0000-0000-0000-000000000001")
OTHER_SELLER_ID = UUID("bb000000-0000-0000-0000-000000000001")
CATEGORY_ID = UUID("cc000000-0000-0000-0000-000000000001")


class DbState:
    def __init__(self, session_factory, products: dict[str, UUID]) -> None:
        self.session_factory = session_factory
        self.products = products


def _make_product(
    seller_id: UUID,
    *,
    title: str,
    status: ProductStatus = ProductStatus.MODERATED,
    deleted: bool = False,
    price: int = 10000,
) -> Product:
    now = datetime.now(UTC)
    p = Product(
        id=uuid4(),
        seller_id=seller_id,
        title=title,
        slug=title.lower().replace(" ", "-"),
        description="desc",
        status=status,
        category_id=CATEGORY_ID,
        images=[{"url": "https://example.com/img.jpg", "ordering": 0}],
        characteristics=[],
        deleted=deleted,
        created_at=now,
        updated_at=now,
    )
    p.skus = [
        SKU(
            id=uuid4(),
            product_id=p.id,
            name="SKU",
            price=price,
            discount=0,
            stock_quantity=5,
            active_quantity=5,
            reserved_quantity=0,
            images=[],
            characteristics=[],
            created_at=now,
            updated_at=now,
        )
    ]
    return p


@pytest.fixture()
def db_state(tmp_path: Path) -> Generator[DbState]:
    db_path = tmp_path / "list_products.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> dict[str, UUID]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        now = datetime.now(UTC)
        products: dict[str, UUID] = {}
        async with session_factory() as session:
            session.add(
                Category(
                    id=CATEGORY_ID,
                    name="Electronics",
                    parent_id=None,
                    level=0,
                    path="/electronics",
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            own = _make_product(SELLER_ID, title="My Product", price=5000)
            own_blocked = _make_product(
                SELLER_ID, title="Blocked Product", status=ProductStatus.BLOCKED
            )
            own_deleted = _make_product(SELLER_ID, title="Deleted Product", deleted=True)
            other = _make_product(OTHER_SELLER_ID, title="Other Seller Product")
            search_match = _make_product(SELLER_ID, title="Apple iPhone Case")

            session.add_all([own, own_blocked, own_deleted, other, search_match])
            await session.commit()

            products["own"] = own.id
            products["own_blocked"] = own_blocked.id
            products["own_deleted"] = own_deleted.id
            products["other"] = other.id
            products["search_match"] = search_match.id

        return products

    products = asyncio.run(prepare())
    state = DbState(session_factory, products)

    original = db_module.SessionLocal
    db_module.SessionLocal = session_factory
    app.dependency_overrides = {}
    app.dependency_overrides[get_current_seller_id] = lambda: SELLER_ID
    try:
        yield state
    finally:
        app.dependency_overrides = {}
        db_module.SessionLocal = original
        asyncio.run(engine.dispose())


@pytest.fixture()
def client(db_state: DbState) -> Generator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_list_returns_only_own_products(client: TestClient, db_state: DbState) -> None:
    response = client.get("/api/v1/products")

    assert response.status_code == 200
    payload = response.json()
    ids = {item["id"] for item in payload["items"]}
    assert str(db_state.products["own"]) in ids
    assert str(db_state.products["other"]) not in ids


def test_idor_query_param_seller_id_ignored(client: TestClient, db_state: DbState) -> None:
    # Passing another seller's id in the query must NOT change the result set.
    response = client.get(f"/api/v1/products?seller_id={OTHER_SELLER_ID}")

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert str(db_state.products["other"]) not in ids
    assert str(db_state.products["own"]) in ids


def test_deleted_products_visible_with_deleted_flag(
    client: TestClient, db_state: DbState
) -> None:
    response = client.get("/api/v1/products?include_deleted=true")

    assert response.status_code == 200
    items = response.json()["items"]
    ids = {item["id"] for item in items}
    assert str(db_state.products["own_deleted"]) in ids
    deleted_item = next(
        i for i in items if i["id"] == str(db_state.products["own_deleted"])
    )
    assert deleted_item["deleted"] is True


def test_status_filter_works_correctly(client: TestClient, db_state: DbState) -> None:
    response = client.get("/api/v1/products?status=BLOCKED")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == str(db_state.products["own_blocked"])
    assert items[0]["status"] == "BLOCKED"


def test_search_by_title_case_insensitive(client: TestClient, db_state: DbState) -> None:
    response = client.get("/api/v1/products?search=apple")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == str(db_state.products["search_match"])
