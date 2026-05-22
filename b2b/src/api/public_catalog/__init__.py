from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db import get_session
from src.models import SKU, Category, Product, ProductStatus

router = APIRouter(prefix="/api/v1/public/products", tags=["public-catalog"])


@router.get("/{product_id}/similar")
async def get_public_similar_products(
    product_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(10, ge=1, le=50),
) -> JSONResponse:
    try:
        product_uuid = UUID(product_id)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Invalid product_id"},
        )

    product = await session.get(Product, product_uuid)
    if product is None:
        return JSONResponse(
            status_code=404,
            content={"code": "NOT_FOUND", "message": "Product not found"},
        )

    category = await session.get(Category, product.category_id)
    if category is None:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_REQUEST", "message": "Nonexistent category id"},
        )

    exclude_ids = {product_uuid}
    items = await _fetch_similar_for_category(
        session,
        category_id=product.category_id,
        exclude_ids=exclude_ids,
        limit=limit,
    )

    if len(items) < limit and category.parent_id is not None:
        remaining = limit - len(items)
        exclude_ids.update({UUID(item["id"]) for item in items})
        items.extend(
            await _fetch_similar_for_category(
                session,
                category_id=category.parent_id,
                exclude_ids=exclude_ids,
                limit=remaining,
            )
        )

    return JSONResponse(content=items)


async def _fetch_similar_for_category(
    session: AsyncSession,
    *,
    category_id: UUID,
    exclude_ids: set[UUID],
    limit: int,
) -> list[dict[str, object]]:
    stmt = (
        select(Product, func.min(SKU.price).label("min_price"))
        .join(SKU)
        .where(Product.category_id == category_id)
        .where(Product.status == ProductStatus.MODERATED)
        .where(SKU.active_quantity > 0)
        .group_by(Product.id)
        .order_by(func.random())
        .limit(limit)
    )
    if exclude_ids:
        stmt = stmt.where(Product.id.notin_(exclude_ids))

    result = await session.execute(stmt)
    return [_product_to_public_short(row[0], row[1]) for row in result.all()]


def _product_to_public_short(product: Product, min_price: int | None) -> dict[str, object]:
    return {
        "id": str(product.id),
        "title": product.title,
        "slug": _slugify(product.title),
        "status": product.status.value,
        "category_id": str(product.category_id),
        "min_price": int(min_price or 0),
        "cover_image": _extract_cover_image(product.images),
        "created_at": product.created_at.isoformat(),
    }


def _extract_cover_image(images: list | None) -> str | None:
    if not images:
        return None
    first = images[0]
    if isinstance(first, dict):
        return str(first.get("url"))
    return str(first)


def _slugify(value: str) -> str:
    return "-".join(part for part in value.lower().strip().split() if part)
