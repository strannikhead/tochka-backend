from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from src.api.category_navigation import (
    CategoryRecord,
    InMemoryCategoryRepository,
    get_category_repository,
)
from src.main import app

ROOT_CATEGORY_ID = UUID("123e4567-e89b-12d3-a456-426614174001")
CHILD_CATEGORY_ID = UUID("123e4567-e89b-12d3-a456-426614174002")
GRANDCHILD_CATEGORY_ID = UUID("123e4567-e89b-12d3-a456-426614174003")
OTHER_ROOT_ID = UUID("123e4567-e89b-12d3-a456-426614174004")
PRODUCT_ID = UUID("770e8400-e29b-41d4-a716-446655441001")
UNKNOWN_CATEGORY_ID = UUID("123e4567-e89b-12d3-a456-426614174099")
ORPHAN_CATEGORY_ID = UUID("123e4567-e89b-12d3-a456-426614174005")
MISSING_PARENT_ID = UUID("123e4567-e89b-12d3-a456-4266141740aa")


def _seed_repository(*, broken: bool = False) -> InMemoryCategoryRepository:
    categories = [
        CategoryRecord(
            id=ROOT_CATEGORY_ID,
            name="Электроника",
            parent_id=None,
            level=0,
            path=("Электроника",),
            slug="electronics",
            description="Категория электроники",
            image_url="https://cdn.example.com/electronics.jpg",
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            updated_at=datetime(2024, 3, 1, 14, 20, tzinfo=UTC),
        ),
        CategoryRecord(
            id=CHILD_CATEGORY_ID,
            name="Смартфоны",
            parent_id=ROOT_CATEGORY_ID,
            level=1,
            path=("Электроника", "Смартфоны"),
            slug="smartphones",
            description="Мобильные телефоны и смартфоны ведущих производителей",
            image_url="https://cdn.example.com/smartphones.jpg",
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            updated_at=datetime(2024, 3, 1, 14, 20, tzinfo=UTC),
        ),
        CategoryRecord(
            id=GRANDCHILD_CATEGORY_ID,
            name="Android",
            parent_id=CHILD_CATEGORY_ID,
            level=2,
            path=("Электроника", "Смартфоны", "Android"),
            slug="android",
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            updated_at=datetime(2024, 3, 1, 14, 20, tzinfo=UTC),
        ),
        CategoryRecord(
            id=OTHER_ROOT_ID,
            name="Одежда",
            parent_id=None,
            level=0,
            path=("Одежда",),
            slug="clothing",
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            updated_at=datetime(2024, 3, 1, 14, 20, tzinfo=UTC),
        ),
    ]
    if broken:
        categories.append(
            CategoryRecord(
                id=ORPHAN_CATEGORY_ID,
                name="Сломанная",
                parent_id=MISSING_PARENT_ID,
                level=1,
                path=("Сломанная",),
                slug="broken",
                created_at=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
                updated_at=datetime(2024, 3, 1, 14, 20, tzinfo=UTC),
            )
        )
    return InMemoryCategoryRepository(
        categories=categories,
        product_categories={PRODUCT_ID: CHILD_CATEGORY_ID},
    )


def _override_repository(repository: InMemoryCategoryRepository) -> None:
    app.dependency_overrides[get_category_repository] = lambda: repository


def test_category_tree_returns_nested_structure(client: TestClient) -> None:
    _override_repository(_seed_repository())

    response = client.get("/api/v1/categories")

    assert response.status_code == 200
    payload = response.json()
    assert [item["name"] for item in payload["items"]] == ["Электроника", "Одежда"]
    electronics = payload["items"][0]
    assert electronics["children"][0]["name"] == "Смартфоны"
    assert electronics["children"][0]["children"][0]["name"] == "Android"


def test_breadcrumbs_return_path_from_root(client: TestClient) -> None:
    _override_repository(_seed_repository())

    response = client.get(
        "/api/v1/breadcrumbs", params={"category_id": str(GRANDCHILD_CATEGORY_ID)}
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["name"] for item in payload["data"]] == ["Электроника", "Смартфоны", "Android"]
    assert [item["url"] for item in payload["data"]] == [
        "/catalog/electronics",
        "/catalog/electronics/smartphones",
        "/catalog/electronics/smartphones/android",
    ]
    assert payload["meta"]["resolved_via"] == "category_id"
    assert payload["meta"]["category_id"] == str(GRANDCHILD_CATEGORY_ID)


def test_breadcrumbs_return_path_from_product(client: TestClient) -> None:
    _override_repository(_seed_repository())

    response = client.get("/api/v1/breadcrumbs", params={"product_id": str(PRODUCT_ID)})

    assert response.status_code == 200
    payload = response.json()
    assert [item["name"] for item in payload["data"]] == ["Электроника", "Смартфоны"]
    assert payload["meta"]["resolved_via"] == "product_id"
    assert payload["meta"]["product_id"] == str(PRODUCT_ID)


def test_category_detail_returns_expected_fields(client: TestClient) -> None:
    _override_repository(_seed_repository())

    response = client.get(
        f"/api/v1/categories/{CHILD_CATEGORY_ID}", params={"include_product_count": "true"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(CHILD_CATEGORY_ID)
    assert payload["name"] == "Смартфоны"
    assert payload["slug"] == "smartphones"
    assert payload["parent"]["id"] == str(ROOT_CATEGORY_ID)
    assert payload["product_count"] == 1
    assert payload["is_active"] is True


def test_ambiguous_params_returns_400(client: TestClient) -> None:
    _override_repository(_seed_repository())

    response = client.get(
        "/api/v1/breadcrumbs",
        params={"category_id": str(CHILD_CATEGORY_ID), "product_id": str(PRODUCT_ID)},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "ambiguous_param"
    assert payload["message"] == "only one of category_id or product_id must be provided"


def test_missing_params_returns_400(client: TestClient) -> None:
    _override_repository(_seed_repository())

    response = client.get("/api/v1/breadcrumbs")

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "missing_param"
    assert payload["message"] == "category_id or product_id must be provided"


def test_unknown_category_returns_404(client: TestClient) -> None:
    _override_repository(_seed_repository())

    response = client.get(f"/api/v1/categories/{UNKNOWN_CATEGORY_ID}")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "NOT_FOUND"
    assert payload["message"] == "Category not found"


def test_orphan_node_returns_422(client: TestClient) -> None:
    _override_repository(_seed_repository(broken=True))

    response = client.get(f"/api/v1/categories/{ORPHAN_CATEGORY_ID}")

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "orphan_node"
    assert payload["message"] == "category hierarchy is broken"


def test_orphan_node_returns_422_for_tree(client: TestClient) -> None:
    _override_repository(_seed_repository(broken=True))

    response = client.get("/api/v1/categories")

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "orphan_node"
    assert payload["message"] == "category hierarchy is broken"
