from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/products", tags=["products"])

_CATALOG_PRODUCTS: list[dict[str, Any]] = [
    {
        "id": UUID("770e8400-e29b-41d4-a716-446655440001"),
        "title": "iPhone 15 Pro Max",
        "image": "https://i.pinimg.com/736x/a6/f9/e9/a6f9e975d2cae3463d66d7a40a6cfe23.jpg",
        "price": 129990,
        "category_id": UUID("2c4e1c32-9e37-4c86-9e5a-0d3a6fa3b4c1"),
        "status": "MODERATED",
        "deleted": False,
        "active_quantity": 7,
        "rating": 4.8,
        "popularity": 210,
        "discount": 0,
        "created_at": datetime(2024, 9, 15, tzinfo=UTC),
        "attributes": {"brand": "Apple", "color": "Black", "memory": "256"},
    },
    {
        "id": UUID("770e8400-e29b-41d4-a716-446655440002"),
        "title": "iPhone 14 Pro",
        "image": "https://images.steamusercontent.com/ugc/1248008971461813591/136B1A9E56BD56F0453117B4561B1B942AC93024/?imw=512",
        "price": 99990,
        "category_id": UUID("2c4e1c32-9e37-4c86-9e5a-0d3a6fa3b4c1"),
        "status": "MODERATED",
        "deleted": False,
        "active_quantity": 0,
        "rating": 4.5,
        "popularity": 180,
        "discount": 10,
        "created_at": datetime(2024, 3, 20, tzinfo=UTC),
        "attributes": {"brand": "Apple", "color": "Silver", "memory": "128"},
    },
    {
        "id": UUID("770e8400-e29b-41d4-a716-446655440003"),
        "title": "Galaxy S24",
        "image": "https://i.pinimg.com/736x/f3/2c/aa/f32caa5f50c4c9bdc1fe4d4a5a30f6e4.jpg",
        "price": 89990,
        "category_id": UUID("2c4e1c32-9e37-4c86-9e5a-0d3a6fa3b4c1"),
        "status": "BLOCKED",
        "deleted": False,
        "active_quantity": 12,
        "rating": 4.3,
        "popularity": 120,
        "discount": 5,
        "created_at": datetime(2024, 6, 2, tzinfo=UTC),
        "attributes": {"brand": "Samsung", "color": "Gray", "memory": "256"},
    },
    {
        "id": UUID("770e8400-e29b-41d4-a716-446655440004"),
        "title": "Pixel 9",
        "image": "https://i.pinimg.com/736x/1b/39/7f/1b397f2ee1c9e0ebf2f49e0b0912a021.jpg",
        "price": 79990,
        "category_id": UUID("2c4e1c32-9e37-4c86-9e5a-0d3a6fa3b4c1"),
        "status": "MODERATED",
        "deleted": True,
        "active_quantity": 5,
        "rating": 4.1,
        "popularity": 90,
        "discount": 0,
        "created_at": datetime(2024, 5, 14, tzinfo=UTC),
        "attributes": {"brand": "Google", "color": "White", "memory": "128"},
    },
]

_ALLOWED_SORTS = {
    "rating": ("rating", True),
    "popularity": ("popularity", True),
    "price_asc": ("price", False),
    "price_desc": ("price", True),
    "date_desc": ("created_at", True),
    "discount_desc": ("discount", True),
}


@router.post("")
async def create_product() -> dict[str, str]:
    return {"endpoint": "create_product"}


@router.get("")
async def list_products(
    request: Request,
    category_id: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    category_uuid = None
    if category_id is not None:
        try:
            category_uuid = UUID(category_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Некорректный id категории") from exc

    filters = _parse_filters(request)
    visible = [
        product
        for product in _CATALOG_PRODUCTS
        if _is_visible(product)
        and _matches_category(product, category_uuid)
        and _matches_filters(product, filters)
    ]

    if category_uuid is not None and not _category_exists(category_uuid):
        raise HTTPException(status_code=404, detail="Категория не найдена")

    sorted_products = _sort_products(visible, sort)
    total_count = len(sorted_products)
    paginated = sorted_products[offset : offset + limit]

    items = [
        {
            "id": str(product["id"]),
            "title": product["title"],
            "image": product["image"],
            "price": product["price"],
            "in_stock": bool(product["active_quantity"]),
            "is_in_cart": False,
        }
        for product in paginated
    ]

    return JSONResponse(
        content={
            "items": items,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    )


@router.get("/{id}")
async def get_product(id: str):
    try:
        product_id = UUID(id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id товара") from exc

    if str(product_id) == "770e8400-e29b-41d4-a716-446655440099":
        raise HTTPException(status_code=404, detail="Товар не найден")

    return JSONResponse(
        content={
            "id": str(product_id),
            "slug": "iphone-15-pro-max",
            "title": "iPhone 15 Pro Max",
            "description": "Флагманский смартфон Apple 2024 года с чипом A17 Pro",
            "images": [
                {
                    "url": "https://images.steamusercontent.com/ugc/1248008971461813591/136B1A9E56BD56F0453117B4561B1B942AC93024/?imw=512&amp;&amp;ima=fit&amp;impolicy=Letterbox&amp;imcolor=%23000000&amp;letterbox=false",
                    "ordering": 0,
                },
                {
                    "url": "https://i.pinimg.com/736x/a6/f9/e9/a6f9e975d2cae3463d66d7a40a6cfe23.jpg",
                    "ordering": 1,
                },
            ],
            "status": "MODERATED",
            "characteristics": [
                {"name": "Бренд", "value": "Apple"},
                {"name": "Страна-производитель", "value": "Китай"},
            ],
            "skus": [
                {
                    "id": "660e8400-e29b-41d4-a716-446655440001",
                    "name": "256GB Black",
                    "price": 12999000,
                    "discount": 0,
                    "image": "/s3/iphone15-black-256.jpg",
                    "active_quantity": 10,
                    "cost_price": 9990000,
                    "reserved_quantity": 2,
                    "characteristics": [
                        {"name": "Цвет", "value": "Чёрный"},
                        {"name": "Объём памяти", "value": "256 ГБ"},
                    ],
                },
                {
                    "id": "660e8400-e29b-41d4-a716-446655440002",
                    "name": "256GB White",
                    "price": 12999000,
                    "discount": 500000,
                    "image": "/s3/iphone15-white-256.jpg",
                    "active_quantity": 0,
                    "cost_price": 9990000,
                    "reserved_quantity": 0,
                    "characteristics": [
                        {"name": "Цвет", "value": "Белый"},
                        {"name": "Объём памяти", "value": "256 ГБ"},
                    ],
                },
            ],
        }
    )


@router.put("/{id}")
async def update_product(id: str) -> dict[str, str]:
    return {"endpoint": "update_product"}


def _parse_filters(request: Request) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        if not key.startswith("filters[") or not key.endswith("]"):
            continue
        name = key[len("filters[") : -1].strip()
        if not name:
            continue
        filters.setdefault(name, []).append(value)
    return filters


def _is_visible(product: dict[str, Any]) -> bool:
    return (
        product.get("status") == "MODERATED"
        and product.get("deleted") is False
        and int(product.get("active_quantity") or 0) > 0
    )


def _matches_category(product: dict[str, Any], category_id: UUID | None) -> bool:
    if category_id is None:
        return True
    return product.get("category_id") == category_id


def _matches_filters(product: dict[str, Any], filters: dict[str, list[str]]) -> bool:
    attributes = product.get("attributes") or {}
    for key, values in filters.items():
        if not values:
            continue
        product_value = str(attributes.get(key, "")).strip().lower()
        allowed = {str(value).strip().lower() for value in values}
        if product_value not in allowed:
            return False
    return True


def _sort_products(products: list[dict[str, Any]], sort: str | None) -> list[dict[str, Any]]:
    sort_key, reverse = _ALLOWED_SORTS.get(sort or "rating", _ALLOWED_SORTS["rating"])

    def key_func(item: dict[str, Any]) -> Any:
        value = item.get(sort_key)
        # normalize None to a value comparable with numbers/strings
        if value is None:
            return -999999999 if isinstance(value, (int, float)) else ""
        return value

    return sorted(products, key=key_func, reverse=reverse)


def _category_exists(category_id: UUID) -> bool:
    return any(product["category_id"] == category_id for product in _CATALOG_PRODUCTS)
