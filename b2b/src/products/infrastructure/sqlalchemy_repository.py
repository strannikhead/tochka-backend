from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from b2b.src.models import SKU, Category, OutboxEvent, Product, ProductStatus
from b2b.src.products.domain.errors import (
    CategoryNotFoundError,
    ProductHardBlockedError,
    ProductNotFoundError,
    ProductNotOwnedError,
    SkuNotFoundError,
    SkuNotOwnedError,
)
from b2b.src.products.domain.models import (
    CreateProductCommand,
    ProductListItem,
    ProductListResponse,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class SqlAlchemyProductsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def category_exists(self, category_id: UUID) -> bool:
        stmt = select(func.count()).select_from(Category).where(Category.id == category_id)
        count = await self._session.execute(stmt)
        return int(count.scalar() or 0) > 0

    async def create_product(self, command: CreateProductCommand) -> Product:
        product = Product(
            seller_id=command.seller_id,
            title=command.title,
            slug=command.slug,
            description=command.description,
            category_id=command.category_id,
            status=ProductStatus.CREATED,
            images=[{"url": image.url, "ordering": image.ordering} for image in command.images],
            characteristics=[
                {"name": char.name, "value": char.value} for char in command.characteristics
            ],
        )
        self._session.add(product)
        await self._session.commit()
        await self._session.refresh(product)
        return product

    async def get_product(self, product_id: UUID) -> Product | None:
        stmt = select(Product).where(Product.id == product_id).options(selectinload(Product.skus))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def update_product(
        self,
        product_id: UUID,
        seller_id: UUID,
        changes: dict[str, object],
    ) -> Product:
        stmt = select(Product).where(Product.id == product_id).options(selectinload(Product.skus))
        product = (await self._session.execute(stmt)).scalar_one_or_none()
        if product is None:
            raise ProductNotFoundError("Товар не найден")
        if product.seller_id != seller_id:
            raise ProductNotOwnedError("Product does not belong to the authenticated seller")
        if product.status == ProductStatus.HARD_BLOCKED:
            raise ProductHardBlockedError("Cannot edit hard-blocked product")
        if product.status == ProductStatus.DELETED:
            raise ProductNotFoundError("Товар не найден")

        if "category_id" in changes:
            category_id = changes["category_id"]
            if category_id is not None:
                if not await self.category_exists(category_id):
                    raise CategoryNotFoundError("Категория не найдена")
                product.category_id = category_id

        for field_name in ("title", "description", "characteristics"):
            if field_name in changes and changes[field_name] is not None:
                setattr(product, field_name, changes[field_name])

        if product.status in {ProductStatus.MODERATED, ProductStatus.BLOCKED}:
            product.status = ProductStatus.ON_MODERATION
            product.blocking_reason_id = None
            product.moderator_comment = None
            self._session.add(_build_edit_outbox_event(product.id, product.seller_id))

        await self._session.commit()
        return product

    async def update_sku(
        self,
        sku_id: UUID,
        seller_id: UUID,
        changes: dict[str, object],
    ) -> SKU:
        stmt = select(SKU).where(SKU.id == sku_id).options(selectinload(SKU.product))
        sku = (await self._session.execute(stmt)).scalar_one_or_none()
        if sku is None or sku.product is None:
            raise SkuNotFoundError("SKU not found")
        if sku.product.seller_id != seller_id:
            raise SkuNotOwnedError("SKU does not belong to the authenticated seller")
        if sku.product.status == ProductStatus.HARD_BLOCKED:
            raise ProductHardBlockedError("Cannot edit hard-blocked product")
        if sku.product.status == ProductStatus.DELETED:
            raise SkuNotFoundError("SKU not found")

        for field_name in (
            "name",
            "price",
            "discount",
            "cost_price",
            "article",
            "characteristics",
        ):
            if field_name in changes and changes[field_name] is not None:
                setattr(sku, field_name, changes[field_name])

        if sku.product.status in {ProductStatus.MODERATED, ProductStatus.BLOCKED}:
            sku.product.status = ProductStatus.ON_MODERATION
            sku.product.blocking_reason_id = None
            sku.product.moderator_comment = None
            self._session.add(_build_edit_outbox_event(sku.product.id, sku.product.seller_id))

        await self._session.commit()
        return sku

    async def list_products(
        self,
        *,
        category_id: UUID | None,
        filters: dict[str, list[str]],
        sort: str | None,
        limit: int,
        offset: int,
        search: str | None,
    ) -> ProductListResponse:
        where_clauses = [Product.status == ProductStatus.MODERATED, SKU.active_quantity > 0]
        if category_id is not None:
            where_clauses.append(Product.category_id == category_id)

        if search:
            escaped = _escape_like(search)
            like_pattern = f"%{escaped}%"
            lowered = search.lower()
            where_clauses.append(
                or_(
                    func.lower(Product.title).op("%")(lowered),
                    func.lower(Product.description).op("%")(lowered),
                    Product.title.ilike(like_pattern, escape="\\"),
                    Product.description.ilike(like_pattern, escape="\\"),
                )
            )

        where_clauses.extend(_build_characteristic_filters(filters))

        count_stmt = (
            select(func.count(func.distinct(Product.id)))
            .select_from(Product)
            .join(SKU)
            .where(*where_clauses)
        )
        total_count = int((await self._session.execute(count_stmt)).scalar() or 0)

        min_price = func.min(SKU.price).label("min_price")
        stmt = select(Product, min_price).join(SKU).where(*where_clauses).group_by(Product.id)
        stmt = _apply_sort(stmt, sort, min_price)
        stmt = stmt.limit(limit).offset(offset)

        result = await self._session.execute(stmt)
        items = [
            ProductListItem(
                id=product.id,
                title=product.title,
                image=_extract_cover_image(product.images),
                price=int(price or 0),
                in_stock=True,
                is_in_cart=False,
            )
            for product, price in result.all()
        ]

        return ProductListResponse(
            items=tuple(items),
            total_count=total_count,
            limit=limit,
            offset=offset,
        )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_characteristic_filters(filters: dict[str, list[str]]) -> list[Any]:
    conditions: list[Any] = []
    for key, values in filters.items():
        if not values:
            continue
        or_conditions = [
            Product.characteristics.contains([{"name": key, "value": str(value)}])
            for value in values
        ]
        conditions.append(or_(*or_conditions))
    return conditions


def _apply_sort(stmt, sort: str | None, min_price) -> Any:
    sort_key, reverse = _ALLOWED_SORTS.get(sort or "rating", _ALLOWED_SORTS["rating"])
    if sort_key == "min_price":
        order = min_price.desc() if reverse else min_price.asc()
        return stmt.order_by(order)
    order = Product.created_at.desc() if reverse else Product.created_at.asc()
    return stmt.order_by(order)


def _extract_cover_image(images: list | None) -> str:
    if not images:
        return ""
    first = images[0]
    if isinstance(first, dict):
        return str(first.get("url") or "")
    return str(first)


_ALLOWED_SORTS = {
    "rating": ("created_at", True),
    "popularity": ("created_at", True),
    "price_asc": ("min_price", False),
    "price_desc": ("min_price", True),
    "date_desc": ("created_at", True),
    "discount_desc": ("created_at", True),
}


def _build_edit_outbox_event(product_id: UUID, seller_id: UUID) -> OutboxEvent:
    now = datetime.now(UTC)
    idempotency_key = uuid4()
    return OutboxEvent(
        event_type="EDITED",
        aggregate_type="product",
        aggregate_id=product_id,
        idempotency_key=idempotency_key,
        payload={
            "idempotency_key": str(idempotency_key),
            "product_id": str(product_id),
            "seller_id": str(seller_id),
            "event": "EDITED",
            "date": now.isoformat(),
        },
    )
