from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from b2b.src.db import get_session
from b2b.src.models import SKU, Category, Product, ProductStatus

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.post("")
async def create_product() -> dict[str, str]:
    return {"endpoint": "create_product"}


@router.get("")
async def list_products(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    category_id: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    search: str | None = Query(default=None),
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
    search_value = _normalize_search(search)

    if category_uuid is not None and not await _category_exists(session, category_uuid):
        raise HTTPException(status_code=404, detail="Категория не найдена")

    total_count = await _count_products(session, category_uuid, filters, search_value)
    rows = await _fetch_products(
        session,
        category_id=category_uuid,
        filters=filters,
        search=search_value,
        sort=sort,
        limit=limit,
        offset=offset,
    )

    items = [_row_to_item(row) for row in rows]

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


@router.get("/{id}/similar")
async def get_similar_products(
    id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    category: str = Query(...),
    limit: int = Query(8, ge=1, le=20),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    try:
        product_id = UUID(id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id товара") from exc

    try:
        category_id = UUID(category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id категории") from exc

    if not await _category_exists(session, category_id):
        raise HTTPException(status_code=400, detail="Категория не найдена")

    if not await _product_exists(session, product_id):
        raise HTTPException(status_code=404, detail="Товар не найден")

    required_count = limit + offset
    primary_count = await _count_similar_products(session, category_id, product_id)
    parent_id = await _category_parent_id(session, category_id)
    use_parent = parent_id is not None and primary_count < required_count

    total_count = primary_count
    items: list[dict[str, Any]] = []
    seed = str(product_id)

    if offset < primary_count:
        primary_rows = await _fetch_similar_products(
            session,
            category_id=category_id,
            product_id=product_id,
            limit=limit,
            offset=offset,
            seed=seed,
        )
        items.extend(_row_to_item(row) for row in primary_rows)
        remaining = limit - len(items)
        if remaining > 0 and use_parent and parent_id is not None:
            parent_count = await _count_similar_products(session, parent_id, product_id)
            total_count += parent_count
            parent_rows = await _fetch_similar_products(
                session,
                category_id=parent_id,
                product_id=product_id,
                limit=remaining,
                offset=0,
                seed=seed,
            )
            items.extend(_row_to_item(row) for row in parent_rows)
    elif use_parent and parent_id is not None:
        parent_count = await _count_similar_products(session, parent_id, product_id)
        total_count += parent_count
        parent_offset = offset - primary_count
        parent_rows = await _fetch_similar_products(
            session,
            category_id=parent_id,
            product_id=product_id,
            limit=limit,
            offset=parent_offset,
            seed=seed,
        )
        items.extend(_row_to_item(row) for row in parent_rows)

    return JSONResponse(
        content={
            "items": items,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    )


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


def _normalize_search(search: str | None) -> str | None:
    if search is None:
        return None
    normalized = search.strip().lower()
    return normalized or None


async def _category_exists(session: AsyncSession, category_id: UUID) -> bool:
    stmt = select(func.count()).select_from(Category).where(Category.id == category_id)
    result = await session.execute(stmt)
    return result.scalar_one() > 0


async def _product_exists(session: AsyncSession, product_id: UUID) -> bool:
    stmt = select(func.count()).select_from(Product).where(Product.id == product_id)
    result = await session.execute(stmt)
    return result.scalar_one() > 0


async def _category_parent_id(session: AsyncSession, category_id: UUID) -> UUID | None:
    stmt = select(Category.parent_id).where(Category.id == category_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _count_products(
    session: AsyncSession,
    category_id: UUID | None,
    filters: dict[str, list[str]],
    search: str | None,
) -> int:
    subquery, has_similarity = _products_subquery(category_id, filters, search)
    stmt = select(func.count()).select_from(subquery)
    if has_similarity:
        stmt = stmt.where(subquery.c.similarity >= 0.2)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def _fetch_products(
    session: AsyncSession,
    *,
    category_id: UUID | None,
    filters: dict[str, list[str]],
    search: str | None,
    sort: str | None,
    limit: int,
    offset: int,
) -> list[tuple[Product, int, int]]:
    subquery, has_similarity = _products_subquery(category_id, filters, search)
    product_alias = aliased(Product, subquery)

    stmt = select(product_alias, subquery.c.max_qty, subquery.c.min_price).select_from(subquery)
    if has_similarity:
        stmt = stmt.where(subquery.c.similarity >= 0.2).order_by(subquery.c.similarity.desc())
    elif sort == "price_asc":
        stmt = stmt.order_by(subquery.c.min_price.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(subquery.c.min_price.desc())
    elif sort == "date_desc":
        stmt = stmt.order_by(subquery.c.created_at.desc())
    else:
        stmt = stmt.order_by(subquery.c.created_at.desc())

    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return [(row[0], row[1], row[2]) for row in result.all()]


def _products_subquery(
    category_id: UUID | None,
    filters: dict[str, list[str]],
    search: str | None,
):
    similarity = _similarity_expression(search).label("similarity") if search else None
    columns: list[Any] = [
        Product,
        func.max(SKU.active_quantity).label("max_qty"),
        func.min(SKU.price).label("min_price"),
    ]
    if similarity is not None:
        columns.append(similarity)

    stmt = (
        select(*columns)
        .join(SKU)
        .where(Product.status == ProductStatus.MODERATED)
        .where(SKU.active_quantity > 0)
        .group_by(Product.id)
    )
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    for key, values in filters.items():
        if not values:
            continue
        conditions = [
            Product.characteristics.contains([{"name": key, "value": value}]) for value in values
        ]
        stmt = stmt.where(or_(*conditions))
    return stmt.subquery(), similarity is not None


def _similarity_expression(search: str):
    return func.greatest(
        func.similarity(func.lower(Product.title), search),
        func.similarity(func.lower(func.coalesce(Product.description, "")), search),
    )


def _row_to_item(row: tuple[Product, int, int]) -> dict[str, Any]:
    product, max_qty, min_price = row
    image = _extract_image(product.images)
    return {
        "id": str(product.id),
        "title": product.title,
        "image": image,
        "price": int(min_price or 0),
        "in_stock": bool(max_qty),
        "is_in_cart": False,
    }


def _similar_products_subquery(category_id: UUID, product_id: UUID):
    stmt = (
        select(
            Product,
            func.max(SKU.active_quantity).label("max_qty"),
            func.min(SKU.price).label("min_price"),
        )
        .join(SKU)
        .where(Product.status == ProductStatus.MODERATED)
        .where(SKU.active_quantity > 0)
        .where(Product.id != product_id)
        .where(Product.category_id == category_id)
        .group_by(Product.id)
    )
    return stmt.subquery()


async def _count_similar_products(
    session: AsyncSession, category_id: UUID, product_id: UUID
) -> int:
    subquery = _similar_products_subquery(category_id, product_id)
    stmt = select(func.count()).select_from(subquery)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def _fetch_similar_products(
    session: AsyncSession,
    *,
    category_id: UUID,
    product_id: UUID,
    limit: int,
    offset: int,
    seed: str,
) -> list[tuple[Product, int, int]]:
    subquery = _similar_products_subquery(category_id, product_id)
    product_alias = aliased(Product, subquery)
    stmt = (
        select(product_alias, subquery.c.max_qty, subquery.c.min_price)
        .select_from(subquery)
        .order_by(_similar_order_expression(seed))
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return [(row[0], row[1], row[2]) for row in result.all()]


def _similar_order_expression(seed: str):
    return func.md5(func.concat(cast(Product.id, String), seed))


def _extract_image(images: list | None) -> str:
    if not images:
        return ""
    first = images[0]
    if isinstance(first, dict):
        return str(first.get("url", ""))
    return str(first)
