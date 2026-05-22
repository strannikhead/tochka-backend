from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from src.api.cart.dependencies import get_b2b_cart_client, get_cart_repository
from src.api.dependencies import get_optional_user_id
from src.cart.b2b_client import InMemoryB2BCartClient
from src.cart.domain import B2BSkuData, CartItemStored
from src.cart.repository import InMemoryCartRepository
from src.main import app

PRODUCT_ID_1 = uuid4()
PRODUCT_ID_2 = uuid4()
SKU_ID_1 = uuid4()
SKU_ID_2 = uuid4()
SKU_ID_UNAVAILABLE = uuid4()
SESSION_ID = uuid4()


def make_sku(
    sku_id: UUID,
    product_id: UUID,
    *,
    name: str = "Default SKU",
    price: int = 10000,
    stock: int = 5,
    product_status: str = "MODERATED",
    product_title: str = "Test Product",
    sku_code: str | None = "TST-001",
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
        sku_code=sku_code,
    )


def setup_overrides(
    repo: InMemoryCartRepository,
    b2b: InMemoryB2BCartClient,
    *,
    user_id: UUID | None = None,
) -> None:
    app.dependency_overrides[get_cart_repository] = lambda: repo
    app.dependency_overrides[get_b2b_cart_client] = lambda: b2b
    app.dependency_overrides[get_optional_user_id] = lambda: user_id


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides = {}


def test__add_sku_increments_quantity_if_already_in_cart() -> None:
    user_id = uuid4()
    repo = InMemoryCartRepository()
    b2b = InMemoryB2BCartClient(skus={SKU_ID_1: make_sku(SKU_ID_1, PRODUCT_ID_1, stock=20)})
    setup_overrides(repo, b2b, user_id=user_id)

    with TestClient(app) as client:
        r1 = client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_1), "quantity": 2},
        )
        assert r1.status_code == 200
        data1 = r1.json()
        assert len(data1["items"]) == 1
        assert data1["items"][0]["quantity"] == 2
        assert data1["items_count"] == 2

        r2 = client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_1), "quantity": 3},
        )
        assert r2.status_code == 200
        data2 = r2.json()
        assert len(data2["items"]) == 1
        assert data2["items"][0]["quantity"] == 5
        assert data2["items_count"] == 5


def test__get_cart_enriched_with_b2b_data() -> None:
    user_id = uuid4()
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
    setup_overrides(repo, b2b, user_id=user_id)

    with TestClient(app) as client:
        client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_1), "quantity": 1},
        )

        r = client.get("/api/v1/cart")
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["name"] == "iPhone 15 256GB Black"
        assert item["unit_price"] == 12999000
        assert item["line_total"] == 12999000
        assert item["available_quantity"] == 5
        assert item["is_available"] is True
        assert data["items_count"] == 1
        assert data["subtotal"] == 12999000
        assert data["is_valid"] is True


def test__unavailable_sku_shown_with_reason() -> None:
    user_id = uuid4()
    repo = InMemoryCartRepository()
    b2b = InMemoryB2BCartClient(
        skus={SKU_ID_UNAVAILABLE: make_sku(SKU_ID_UNAVAILABLE, PRODUCT_ID_2, stock=0)},
    )
    setup_overrides(repo, b2b, user_id=user_id)

    item_id = uuid4()
    now = datetime.now(UTC)
    repo._items[item_id] = CartItemStored(
        id=item_id,
        user_id=user_id,
        session_id=None,
        sku_id=SKU_ID_UNAVAILABLE,
        quantity=1,
        added_at=now,
        updated_at=now,
    )

    with TestClient(app) as client:
        r = client.get("/api/v1/cart")
        assert r.status_code == 200
        data = r.json()
        items = data["items"]
        assert len(items) == 1
        item = items[0]
        assert item["is_available"] is False
        assert item["available_quantity"] == 0
        assert item["line_total"] == 0
        assert data["subtotal"] == 0
        assert data["is_valid"] is False

        validate_r = client.post("/api/v1/cart/validate")
        assert validate_r.status_code == 200
        validate_data = validate_r.json()
        assert validate_data["is_valid"] is False
        assert len(validate_data["issues"]) == 1
        issue = validate_data["issues"][0]
        assert issue["sku_id"] == str(SKU_ID_UNAVAILABLE)
        assert issue["type"] == "OUT_OF_STOCK"


def test__guest_cart_merged_on_login() -> None:
    """Merge при конфликте берёт MAX(guest, auth)."""
    user_id = uuid4()
    repo = InMemoryCartRepository()
    b2b = InMemoryB2BCartClient(
        skus={
            SKU_ID_1: make_sku(SKU_ID_1, PRODUCT_ID_1, stock=20),
            SKU_ID_2: make_sku(SKU_ID_2, PRODUCT_ID_2, stock=20),
        }
    )
    setup_overrides(repo, b2b, user_id=None)

    with TestClient(app) as client:
        # Guest adds SKU_1 (qty=5) and SKU_2 (qty=1) via X-Session-Id
        client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_1), "quantity": 5},
            headers={"X-Session-Id": str(SESSION_ID)},
        )
        client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_2), "quantity": 1},
            headers={"X-Session-Id": str(SESSION_ID)},
        )

        # Authorized user already has SKU_1 (qty=2)
        app.dependency_overrides[get_optional_user_id] = lambda: user_id
        client.post(
            "/api/v1/cart/items",
            json={"sku_id": str(SKU_ID_1), "quantity": 2},
        )

        # Merge after login: JWT user + X-Session-Id header
        merge_r = client.post(
            "/api/v1/cart/merge",
            headers={"X-Session-Id": str(SESSION_ID)},
        )
        assert merge_r.status_code == 200
        merged = merge_r.json()
        quantities = {item["sku_id"]: item["quantity"] for item in merged["items"]}

        # Conflict: MAX(guest=5, auth=2) = 5
        assert quantities[str(SKU_ID_1)] == 5
        # Transferred from guest (no conflict)
        assert quantities[str(SKU_ID_2)] == 1

        # Guest cart should be empty
        app.dependency_overrides[get_optional_user_id] = lambda: None
        r_guest = client.get("/api/v1/cart", headers={"X-Session-Id": str(SESSION_ID)})
        assert r_guest.status_code == 200
        assert r_guest.json()["items"] == []
