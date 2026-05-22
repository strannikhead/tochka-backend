from __future__ import annotations

from uuid import UUID

DEFAULT_CATEGORY_ID = UUID("2c4e1c32-9e37-4c86-9e5a-0d3a6fa3b4c1")
SMARTPHONES_CATEGORY_ID = UUID("123e4567-e89b-12d3-a456-426614174001")
LAPTOPS_CATEGORY_ID = UUID("123e4567-e89b-12d3-a456-426614174002")


def _category_ref(
    category_id: UUID,
    name: str,
    *,
    parent_id: UUID | None,
    level: int,
    path: list[str],
) -> dict[str, object]:
    return {
        "id": str(category_id),
        "name": name,
        "parent_id": str(parent_id) if parent_id is not None else None,
        "level": level,
        "path": path,
    }


CATEGORIES: list[dict[str, object]] = [
    _category_ref(
        DEFAULT_CATEGORY_ID,
        "Electronics",
        parent_id=None,
        level=0,
        path=["Electronics"],
    ),
    _category_ref(
        SMARTPHONES_CATEGORY_ID,
        "Smartphones",
        parent_id=DEFAULT_CATEGORY_ID,
        level=1,
        path=["Electronics", "Smartphones"],
    ),
    _category_ref(
        LAPTOPS_CATEGORY_ID,
        "Laptops",
        parent_id=DEFAULT_CATEGORY_ID,
        level=1,
        path=["Electronics", "Laptops"],
    ),
]


CATEGORY_TREE: list[dict[str, object]] = [
    {
        **CATEGORIES[0],
        "children": [
            {**CATEGORIES[1], "children": []},
            {**CATEGORIES[2], "children": []},
        ],
    }
]


def category_breadcrumbs(category_id: UUID | None = None) -> list[dict[str, object]]:
    target_id = category_id or SMARTPHONES_CATEGORY_ID
    if target_id == SMARTPHONES_CATEGORY_ID:
        return [CATEGORIES[0], CATEGORIES[1]]
    if target_id == LAPTOPS_CATEGORY_ID:
        return [CATEGORIES[0], CATEGORIES[2]]
    return [CATEGORIES[0]]


BANNERS: list[dict[str, object]] = [
    {
        "id": "11111111-1111-4111-8111-111111111111",
        "title": "Spring deals",
        "image_url": "https://example.com/banners/spring.jpg",
        "link": "https://example.com/catalog",
        "ordering": 1,
        "active_from": "2026-01-01T00:00:00Z",
        "active_to": "2026-12-31T23:59:59Z",
    },
    {
        "id": "22222222-2222-4222-8222-222222222222",
        "title": "Top picks",
        "image_url": "https://example.com/banners/picks.jpg",
        "link": "https://example.com/catalog?sort=popularity",
        "ordering": 2,
    },
]


def catalog_card(
    *,
    product_id: UUID,
    name: str,
    min_price: int,
    has_stock: bool,
    image_url: str | None = None,
    category_ref: dict[str, object] | None = None,
) -> dict[str, object]:
    images: list[dict[str, object]] = []
    if image_url:
        images.append(
            {
                "id": str(product_id),
                "url": image_url,
                "ordering": 0,
                "is_main": True,
            }
        )

    return {
        "id": str(product_id),
        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "category": category_ref or CATEGORIES[0],
        "min_price": min_price,
        "old_price": None,
        "has_stock": has_stock,
        "rating": 4.8,
        "reviews_count": 0,
        "images": images,
        "seller": {
            "id": "33333333-3333-4333-8333-333333333333",
            "display_name": "NeoMarket",
        },
    }


COLLECTIONS: list[dict[str, object]] = [
    {
        "id": "44444444-4444-4444-8444-444444444444",
        "name": "Hits of the week",
        "description": "Popular picks from the catalog",
        "products": [
            catalog_card(
                product_id=UUID("770e8400-e29b-41d4-a716-446655440002"),
                name="iPhone 15 Pro Max",
                min_price=12999000,
                has_stock=True,
                image_url="https://example.com/images/iphone15.jpg",
            ),
            catalog_card(
                product_id=UUID("770e8400-e29b-41d4-a716-446655440003"),
                name="Samsung Galaxy S24",
                min_price=8999000,
                has_stock=True,
                image_url="https://example.com/images/s24.jpg",
            ),
        ],
    }
]
