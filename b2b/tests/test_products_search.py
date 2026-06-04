"""Search behaviour for GET /api/v1/products (seller cabinet).

Integration tests against SQLite; mirrors the pattern used in test_products_delete.py.
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
from b2b.src.db import SessionLocal
from b2b.src.main import app
from b2b.src.models import SKU, Base, Category, Product, ProductStatus

SELLER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
CATEGORY_ID = UUID("550e8400-e29b-41d4-a716-446655440010")


def _product(title: str) -> Product:
    now = datetime.now(UTC)
    p = Product(
        id=uuid4(),
        seller_id=SELLER_ID,
        title=title,
        slug=title.lower().replace(" ", "-"),
        description="desc",
        status=ProductStatus.MODERATED,
        category_id=CATEGORY_ID,
        images=[],
        characteristics=[],
        deleted=False,
        created_at=now,
        updated_at=now,
    )
    p.skus = [
        SKU(
            id=uuid4(),
            product_id=p.id,
            name="default",
            price=5000,
            discount=0,
            stock_quantity=1,
            active_quantity=1,
            reserved_quantity=0,
            images=[],
            characteristics=[],
            created_at=now,
            updated_at=now,
        )
    ]
    return p


@pytest.fixture()
def db_state(tmp_path: Path) -> Generator[None]:
    db_path = tmp_path / "search.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        now = datetime.now(UTC)
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
            session.add_all([
                _product("Wireless Headphones"),
                _product("Laptop Pro"),
                _product("iPhone%15 Special"),
            ])
            await session.commit()

    asyncio.run(prepare())

    original = db_module.SessionLocal
    db_module.SessionLocal = session_factory
    app.dependency_overrides = {}
    app.dependency_overrides[get_current_seller_id] = lambda: SELLER_ID
    try:
        yield
    finally:
        app.dependency_overrides = {}
        db_module.SessionLocal = original
        asyncio.run(engine.dispose())


@pytest.fixture()
def client(db_state: None) -> Generator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_search_returns_matching_products(client: TestClient) -> None:
    response = client.get("/api/v1/products", params={"search": "wireless"})

    assert response.status_code == 200
    payload = response.json()
    titles = {item["title"] for item in payload["items"]}
    assert "Wireless Headphones" in titles
    assert "Laptop Pro" not in titles


def test_special_chars_do_not_break_query(client: TestClient) -> None:
    response = client.get("/api/v1/products", params={"search": "iPhone%15"})

    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert payload["total_count"] == 1
