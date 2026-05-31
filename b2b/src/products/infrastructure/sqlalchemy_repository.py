from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from b2b.src.models import (
    SKU,
    Category,
    OutboxEvent,
    ProcessedEvent,
    Product,
    ProductStatus,
)
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
    ModerationDecision,
    ProductListItem,
    ProductListResponse,
)


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
        if product.deleted:
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
        if sku.product.deleted:
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

    async def soft_delete_product(self, product_id: UUID, seller_id: UUID) -> Product:
        stmt = select(Product).where(Product.id == product_id).options(selectinload(Product.skus))
        product = (await self._session.execute(stmt)).scalar_one_or_none()
        if product is None:
            raise ProductNotFoundError("Товар не найден")
        if product.seller_id != seller_id:
            raise ProductNotOwnedError("Product does not belong to the authenticated seller")
        if product.status == ProductStatus.HARD_BLOCKED:
            # HARD_BLOCKED is terminal: the seller can no longer edit or delete it.
            raise ProductHardBlockedError("Cannot delete hard-blocked product")
        if product.deleted:
            # Already soft-deleted: no active product to remove -> 404, never a re-delete.
            raise ProductNotFoundError("Товар не найден")

        # Soft delete keeps the row and its moderation status; only the flag flips.
        product.deleted = True
        sku_ids = [sku.id for sku in product.skus]
        # Both cascade events are written to the outbox in the same transaction as the
        # flag, so the delete and its notifications commit atomically (see PR ADR).
        for event in _build_delete_outbox_events(product.id, product.seller_id, sku_ids):
            self._session.add(event)

        await self._session.commit()
        return product

    async def apply_moderation_event(self, decision: ModerationDecision) -> bool:
        """Apply a Moderation decision idempotently. Returns False for a duplicate."""
        already = await self._session.execute(
            select(ProcessedEvent).where(
                ProcessedEvent.sender_service == decision.sender_service,
                ProcessedEvent.idempotency_key == decision.idempotency_key,
            )
        )
        if already.scalar_one_or_none() is not None:
            return False

        stmt = (
            select(Product)
            .where(Product.id == decision.product_id)
            .options(selectinload(Product.skus))
        )
        product = (await self._session.execute(stmt)).scalar_one_or_none()
        if product is not None:
            self._apply_decision(product, decision)

        # The unique (sender_service, idempotency_key) constraint is the real guard:
        # a racing duplicate that passed the SELECT above fails here and is a no-op.
        self._session.add(
            ProcessedEvent(
                sender_service=decision.sender_service,
                idempotency_key=decision.idempotency_key,
                event_type=decision.event_type,
                product_id=decision.product_id,
            )
        )
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return False
        return True

    def _apply_decision(self, product: Product, decision: ModerationDecision) -> None:
        if decision.event_type == "MODERATED":
            # Approval clears all blocking data and makes the card catalog-visible.
            product.status = ProductStatus.MODERATED
            product.blocking_reason_id = None
            product.moderator_comment = None
            product.field_reports = []
            return

        # BLOCKED: hard_block decides between the editable BLOCKED and terminal HARD_BLOCKED.
        product.status = (
            ProductStatus.HARD_BLOCKED if decision.hard_block else ProductStatus.BLOCKED
        )
        product.blocking_reason_id = decision.blocking_reason_id
        product.moderator_comment = decision.moderator_comment
        product.field_reports = [
            {
                "field_name": report.field_name,
                "comment": report.comment,
                "sku_id": str(report.sku_id) if report.sku_id is not None else None,
            }
            for report in decision.field_reports
        ]
        # Cascade PRODUCT_BLOCKED to B2C only when there is sellable stock to pull.
        if any(sku.active_quantity > 0 for sku in product.skus):
            self._session.add(
                _build_product_blocked_outbox_event(
                    product.id,
                    [sku.id for sku in product.skus],
                    hard_block=decision.hard_block,
                    blocking_reason_id=decision.blocking_reason_id,
                )
            )

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
        where_clauses = [
            Product.status == ProductStatus.MODERATED,
            Product.deleted.is_(False),
            SKU.active_quantity > 0,
        ]
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


def _build_product_blocked_outbox_event(
    product_id: UUID,
    sku_ids: list[UUID],
    *,
    hard_block: bool,
    blocking_reason_id: UUID | None,
) -> OutboxEvent:
    now = datetime.now(UTC)
    idempotency_key = uuid4()
    # B2C uses sku_ids to mark the affected cart lines as unavailable.
    return OutboxEvent(
        event_type="PRODUCT_BLOCKED",
        aggregate_type="product",
        aggregate_id=product_id,
        idempotency_key=idempotency_key,
        payload={
            "idempotency_key": str(idempotency_key),
            "product_id": str(product_id),
            "sku_ids": [str(sku_id) for sku_id in sku_ids],
            "hard_block": hard_block,
            "blocking_reason_id": str(blocking_reason_id) if blocking_reason_id else None,
            "event": "PRODUCT_BLOCKED",
            "target": "b2c",
            "date": now.isoformat(),
        },
    )


def _build_delete_outbox_events(
    product_id: UUID, seller_id: UUID, sku_ids: list[UUID]
) -> list[OutboxEvent]:
    now = datetime.now(UTC)
    moderation_key = uuid4()
    b2c_key = uuid4()
    moderation_event = OutboxEvent(
        event_type="DELETED",
        aggregate_type="product",
        aggregate_id=product_id,
        idempotency_key=moderation_key,
        payload={
            "idempotency_key": str(moderation_key),
            "product_id": str(product_id),
            "seller_id": str(seller_id),
            "event": "DELETED",
            "target": "moderation",
            "date": now.isoformat(),
        },
    )
    # B2C needs the sku_ids to mark the corresponding cart lines as unavailable.
    b2c_event = OutboxEvent(
        event_type="PRODUCT_DELETED",
        aggregate_type="product",
        aggregate_id=product_id,
        idempotency_key=b2c_key,
        payload={
            "idempotency_key": str(b2c_key),
            "product_id": str(product_id),
            "sku_ids": [str(sku_id) for sku_id in sku_ids],
            "event": "PRODUCT_DELETED",
            "target": "b2c",
            "date": now.isoformat(),
        },
    )
    return [moderation_event, b2c_event]


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
