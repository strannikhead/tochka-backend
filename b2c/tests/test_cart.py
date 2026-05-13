from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

PROJECT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH))

from src.api.cart.dependencies import get_b2b_cart_client, get_cart_repository
from src.cart.b2b_client import InMemoryB2BCartClient
from src.cart.domain import B2BSkuData, CartItemStored
from src.cart.repository import InMemoryCartRepository
from src.main import app

PRODUCT_ID_1 = uuid4()
PRODUCT_ID_2 = uuid4()
SKU_ID_1 = uuid4()
SKU_ID_2 = uuid4()
SKU_ID_UNAVAILABLE = uuid4()
SESSION_ID = "sess-test-abc123"


def make_sku(
    sku_id: UUID,
    product_id: UUID,
    *,
    name: str = "Default SKU",
    price: int = 10000,
    stock: int = 5,
    product_status: str = "MODERATED",
    product_title: str = "Test Product",
) -> B2BSkuData:
    return B2BSkuData(
        sku_id=sku_id,
        product_id=product_id,
        sku_name=name,
        price=price,
        stock_quantity=stock,
        image_url="/s3/test.jpg",
        product_title=product_title,
        product_status=product_status,
    )


def setup_overrides(repo: InMemoryCartRepository, b2b: InMemoryB2BCartClient) -> None:
    app.dependency_overrides[get_cart_repository] = lambda: repo
    app.dependency_overrides[get_b2b_cart_client] = lambda: b2b


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides = {}


def test__add_sku_increments_quantity_if_already_in_cart() -> None:
    user_id = str(uuid4())
    repo = InMemoryCartRepository()
    b2b = InMemoryB2BCartClient(skus={SKU_ID_1: make_sku(SKU_ID_1, PRODUCT_ID_1, stock=20)})
    setup_overrides(repo, b2b)

    with TestClient(app) as client:
        r1 = client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_1), "quantity": 2},
            headers={"X-User-Id": user_id},
        )
        assert r1.status_code == 201
        assert r1.json()["item"]["quantity"] == 2

        r2 = client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_1), "quantity": 3},
            headers={"X-User-Id": user_id},
        )
        assert r2.status_code == 200
        assert r2.json()["item"]["quantity"] == 5


def test__get_cart_enriched_with_b2b_data() -> None:
    user_id = str(uuid4())
    repo = InMemoryCartRepository()
    b2b = InMemoryB2BCartClient(
        skus={
            SKU_ID_1: make_sku(
                SKU_ID_1,
                PRODUCT_ID_1,
                name="256GB Black",
                price=12999000,
                stock=5,
                product_title="iPhone 15",
            )
        }
    )
    setup_overrides(repo, b2b)

    with TestClient(app) as client:
        client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_1), "quantity": 1},
            headers={"X-User-Id": user_id},
        )

        r = client.get("/api/v1/cart", headers={"X-User-Id": user_id})
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["product_title"] == "iPhone 15"
        assert item["sku_name"] == "256GB Black"
        assert item["unit_price"] == 12999000
        assert item["available"] is True
        assert data["summary"]["total_amount"] == 12999000


def test__unavailable_sku_shown_with_reason() -> None:
    user_id_uuid = uuid4()
    user_id_str = str(user_id_uuid)
    repo = InMemoryCartRepository()
    b2b = InMemoryB2BCartClient(
        skus={
            SKU_ID_UNAVAILABLE: make_sku(SKU_ID_UNAVAILABLE, PRODUCT_ID_2, stock=0),
        }
    )
    setup_overrides(repo, b2b)

    # Insert unavailable item directly into repo, bypassing B2B pre-check
    item_id = uuid4()
    now = datetime.now(UTC)
    repo._items[item_id] = CartItemStored(
        id=item_id,
        user_id=user_id_uuid,
        session_id=None,
        sku_id=SKU_ID_UNAVAILABLE,
        quantity=1,
        added_at=now,
        updated_at=now,
    )

    with TestClient(app) as client:
        r = client.get("/api/v1/cart", headers={"X-User-Id": user_id_str})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["available"] is False
        assert item["unavailable_reason"] == "OUT_OF_STOCK"
        assert item["line_total"] == 0
        assert r.json()["summary"]["total_amount"] == 0
        assert r.json()["summary"]["has_unavailable_items"] is True


def test__guest_cart_merged_on_login() -> None:
    """Merge при конфликте берёт MAX(guest, auth)."""
    user_uuid = uuid4()
    user_id_str = str(user_uuid)

    repo = InMemoryCartRepository()
    b2b = InMemoryB2BCartClient(
        skus={
            SKU_ID_1: make_sku(SKU_ID_1, PRODUCT_ID_1, stock=20),
            SKU_ID_2: make_sku(SKU_ID_2, PRODUCT_ID_2, stock=20),
        }
    )
    setup_overrides(repo, b2b)

    with TestClient(app) as client:
        # Guest adds SKU_1 (qty=5) and SKU_2 (qty=1)
        client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_1), "quantity": 5},
            headers={"X-Session-Id": SESSION_ID},
        )
        client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_2), "quantity": 1},
            headers={"X-Session-Id": SESSION_ID},
        )

        # Authorized user already has SKU_1 (qty=2) — less than guest
        client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_1), "quantity": 2},
            headers={"X-User-Id": user_id_str},
        )

        # Merge after login
        merge_r = client.post(
            "/api/v1/cart/merge",
            json={"session_id": SESSION_ID},
            headers={"X-User-Id": user_id_str},
        )
        assert merge_r.status_code == 200

        # Check merged user cart
        r = client.get("/api/v1/cart", headers={"X-User-Id": user_id_str})
        assert r.status_code == 200
        items = r.json()["items"]
        quantities = {item["sku_id"]: item["quantity"] for item in items}

        # Conflict: MAX(guest=5, auth=2) = 5
        assert quantities[str(SKU_ID_1)] == 5
        # Transferred from guest (no conflict in user cart)
        assert quantities[str(SKU_ID_2)] == 1

        # Guest cart should be empty
        r_guest = client.get("/api/v1/cart", headers={"X-Session-Id": SESSION_ID})
        assert r_guest.status_code == 200
        assert r_guest.json()["items"] == []
