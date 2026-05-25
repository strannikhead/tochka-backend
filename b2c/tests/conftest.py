from __future__ import annotations

import asyncio
import sys
from collections.abc import Generator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PROJECT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH))

from b2b.src.models import SKU as B2BSKU  # noqa: E402
from b2b.src.models import Base as B2BBase  # noqa: E402
from b2b.src.models import Category as B2BCategory  # noqa: E402
from b2b.src.models import Product as B2BProduct  # noqa: E402
from b2b.src.models import ProductStatus as B2BProductStatus  # noqa: E402
from src.api.orders.dependencies import get_checkout_catalog_client  # noqa: E402
from src.main import app  # noqa: E402
from src.orders.db_models import Base as B2COrdersBase  # noqa: E402
from tests.order_test_utils import LiveCheckoutCatalogClient  # noqa: E402


@pytest.fixture()
def test_databases(tmp_path: Path) -> Generator[None]:
    b2b_db_path = tmp_path / "b2b.sqlite3"
    b2c_db_path = tmp_path / "b2c.sqlite3"

    b2b_test_engine = create_async_engine(f"sqlite+aiosqlite:///{b2b_db_path}")
    b2c_test_engine = create_async_engine(f"sqlite+aiosqlite:///{b2c_db_path}")

    async def prepare() -> None:
        async with b2b_test_engine.begin() as conn:
            await conn.run_sync(B2BBase.metadata.create_all)
        async with b2c_test_engine.begin() as conn:
            await conn.run_sync(B2COrdersBase.metadata.create_all)

        async with async_sessionmaker(b2b_test_engine, expire_on_commit=False)() as session:
            await session.execute(delete(B2BSKU))
            await session.execute(delete(B2BProduct))
            await session.execute(delete(B2BCategory))

            category_id = UUID("550e8400-e29b-41d4-a716-446655440010")
            product_id = UUID("550e8400-e29b-41d4-a716-446655440000")
            seller_id = UUID("550e8400-e29b-41d4-a716-446655440000")
            sku_1 = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")
            sku_2 = UUID("8a4e3f9c-1a2b-4c8d-9e5f-6b7a8c9d0e1f")

            session.add(
                B2BCategory(
                    id=category_id,
                    name="Phones",
                    parent_id=None,
                    level=0,
                    path="Phones",
                    is_active=True,
                )
            )

            product = B2BProduct(
                id=product_id,
                seller_id=seller_id,
                title="iPhone 15 Pro Max",
                description="Flagship",
                status=B2BProductStatus.MODERATED,
                category_id=category_id,
                images=[],
                characteristics=[],
            )
            product.skus = [
                B2BSKU(
                    id=sku_1,
                    product_id=product_id,
                    name="256GB Black",
                    price=12999000,
                    active_quantity=10,
                    images=[],
                    characteristics=[],
                ),
                B2BSKU(
                    id=sku_2,
                    product_id=product_id,
                    name="256GB White",
                    price=12999000,
                    active_quantity=4,
                    images=[],
                    characteristics=[],
                ),
            ]
            session.add(product)
            await session.commit()

    asyncio.run(prepare())

    import b2b.src.db as b2b_db_module
    import src.orders.db as b2c_db_module

    b2b_db_module.engine = b2b_test_engine
    b2b_db_module.SessionLocal = async_sessionmaker(b2b_test_engine, expire_on_commit=False)
    b2c_db_module.engine = b2c_test_engine
    b2c_db_module.SessionLocal = async_sessionmaker(b2c_test_engine, expire_on_commit=False)

    try:
        yield
    finally:
        asyncio.run(b2b_test_engine.dispose())
        asyncio.run(b2c_test_engine.dispose())


@pytest.fixture()
def client(test_databases: None) -> Generator[TestClient]:
    app.dependency_overrides = {}
    app.dependency_overrides[get_checkout_catalog_client] = lambda: LiveCheckoutCatalogClient()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}
