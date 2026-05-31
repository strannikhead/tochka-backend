from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from b2b.src.models import SKU, Category, Product, ProductStatus
from b2b.src.public_catalog.domain.errors import (
    CategoryNotFoundError,
    ProductNotFoundError,
)


class PublicCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_catalog(
        self,
        *,
        category_id: UUID | None = None,
        search: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        seller_id: UUID | None = None,
        sort: str = "created_desc",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[tuple[Product, int]], int]:
        min_price_agg = func.min(SKU.price)

        stmt = (
            select(Product, min_price_agg.label("min_price"))
            .join(SKU, SKU.product_id == Product.id)
            .where(
                Product.status == ProductStatus.MODERATED,
                Product.deleted.is_(False),
                SKU.active_quantity > 0,
            )
            .group_by(Product.id)
        )

        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
        if seller_id is not None:
            stmt = stmt.where(Product.seller_id == seller_id)
        if search is not None:
            stmt = stmt.where(Product.title.ilike(f"%{search}%"))
        if min_price is not None:
            stmt = stmt.having(min_price_agg >= min_price)
        if max_price is not None:
            stmt = stmt.having(min_price_agg <= max_price)

        total: int = (
            await self.session.execute(
                select(func.count()).select_from(stmt.subquery())
            )
        ).scalar_one()

        if sort == "price_asc":
            order_col = min_price_agg.asc()
        elif sort == "price_desc":
            order_col = min_price_agg.desc()
        else:
            order_col = Product.created_at.desc()

        rows = (
            await self.session.execute(
                stmt.order_by(order_col).limit(limit).offset(offset)
            )
        ).all()

        return [(row[0], int(row[1] or 0)) for row in rows], total

    async def get_batch(self, product_ids: list[UUID]) -> list[Product]:
        if not product_ids:
            return []

        has_active_sku = (
            select(SKU.id)
            .where(SKU.product_id == Product.id)
            .where(SKU.active_quantity > 0)
            .correlate(Product)
        ).exists()

        stmt = (
            select(Product)
            .options(selectinload(Product.skus))
            .where(
                Product.id.in_(product_ids),
                Product.status == ProductStatus.MODERATED,
                Product.deleted.is_(False),
                has_active_sku,
            )
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_similar(self, product_id: UUID, limit: int) -> list[dict[str, object]]:
        product = await self.session.get(Product, product_id)
        if product is None:
            raise ProductNotFoundError()

        category = await self.session.get(Category, product.category_id)
        if category is None:
            raise CategoryNotFoundError()

        exclude_ids: set[UUID] = {product_id}
        items = await self._fetch_similar_for_category(
            category_id=product.category_id, exclude_ids=exclude_ids, limit=limit
        )

        if len(items) < limit and category.parent_id is not None:
            remaining = limit - len(items)
            exclude_ids.update({UUID(item["id"]) for item in items})
            items.extend(
                await self._fetch_similar_for_category(
                    category_id=category.parent_id, exclude_ids=exclude_ids, limit=remaining
                )
            )

        return items

    async def _fetch_similar_for_category(
        self, category_id: UUID, exclude_ids: set[UUID], limit: int
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

        result = await self.session.execute(stmt)
        return [self._product_to_public_short(row[0], row[1]) for row in result.all()]

    def _product_to_public_short(
        self, product: Product, min_price: int | None
    ) -> dict[str, object]:
        return {
            "id": str(product.id),
            "title": product.title,
            "slug": self._slugify(product.title),
            "status": product.status.value,
            "category_id": str(product.category_id),
            "min_price": int(min_price or 0),
            "cover_image": self._extract_cover_image(product.images),
            "created_at": product.created_at.isoformat(),
        }

    def _extract_cover_image(self, images: list | None) -> str | None:
        if not images:
            return None
        first = images[0]
        if isinstance(first, dict):
            return str(first.get("url"))
        return str(first)

    def _slugify(self, value: str) -> str:
        return "-".join(part for part in value.lower().strip().split() if part)
