from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from b2b.src.b2c_client import B2cClient
from b2b.src.models import SKU, OutboxEvent, OutboxStatus, Product, ProductStatus
from b2b.src.skus.domain.errors import (
    ProductAccessDeniedError,
    ProductHardBlockedError,
    ProductNotFoundError,
    SkuHasActiveReservesError,
    SkuNotFoundError,
)
from b2b.src.skus.infrastructure.moderation_client import ModerationClient

logger = logging.getLogger(__name__)


class SkuService:
    def __init__(
        self,
        session: AsyncSession,
        moderation_client: ModerationClient,
        b2c_client: B2cClient,
    ) -> None:
        self._session = session
        self._moderation_client = moderation_client
        self._b2c_client = b2c_client

    async def create_sku(
        self,
        *,
        product_id: UUID,
        seller_id: UUID,
        name: str,
        price: int,
        discount: int,
        cost_price: int | None,
        article: str | None,
        images: list[dict],
        characteristics: list[dict],
    ) -> SKU:
        product = await self._session.get(Product, product_id)
        if product is None:
            raise ProductNotFoundError(f"Product {product_id} not found")
        if product.seller_id != seller_id:
            raise ProductAccessDeniedError(f"Product {product_id} belongs to another seller")
        if product.status == ProductStatus.HARD_BLOCKED:
            raise ProductHardBlockedError(f"Product {product_id} is hard blocked")

        # Check BEFORE session.add to avoid autoflush counting the new SKU.
        is_first_sku = product.status == ProductStatus.CREATED and not await self._has_skus(
            product_id
        )
        needs_remoderation = product.status in {ProductStatus.MODERATED, ProductStatus.BLOCKED}

        sku = SKU(
            product_id=product_id,
            name=name,
            price=price,
            discount=discount,
            cost_price=cost_price,
            article=article,
            images=images,
            characteristics=characteristics,
        )
        self._session.add(sku)

        outbox_event: OutboxEvent | None = None
        if is_first_sku:
            product.status = ProductStatus.ON_MODERATION
            outbox_event = OutboxEvent(
                idempotency_key=uuid4(),
                product_id=product_id,
                seller_id=seller_id,
                event_type="CREATED",
            )
            self._session.add(outbox_event)
        elif needs_remoderation:
            product.status = ProductStatus.ON_MODERATION
            outbox_event = OutboxEvent(
                idempotency_key=uuid4(),
                product_id=product_id,
                seller_id=seller_id,
                event_type="EDITED",
            )
            self._session.add(outbox_event)

        # Single commit: SKU + status change + outbox record are atomic.
        await self._session.commit()
        await self._session.refresh(sku)

        if outbox_event is not None:
            await self._dispatch_outbox(outbox_event)

        return sku

    async def _dispatch_outbox(self, event: OutboxEvent) -> None:
        """Attempt to send the outbox event to Moderation and mark it SENT.

        On network failure the record stays PENDING — a background worker can retry.
        """
        _dispatch_map = {
            "CREATED": self._moderation_client.send_created_event,
            "EDITED": self._moderation_client.send_edited_event,
            "DELETED": self._moderation_client.send_deleted_event,
        }
        send_fn = _dispatch_map.get(event.event_type)
        if send_fn is None:
            logger.error(
                "Unknown outbox event_type %s for product %s", event.event_type, event.product_id
            )
            return
        try:
            await send_fn(
                idempotency_key=event.idempotency_key,
                product_id=event.product_id,
                seller_id=event.seller_id,
                date=datetime.now(UTC),
            )
            event.status = OutboxStatus.SENT
            event.published_at = datetime.now(UTC)
            self._session.add(event)
            await self._session.commit()
        except Exception:
            logger.exception(
                "Outbox dispatch failed for event %s (product %s); record stays PENDING",
                event.idempotency_key,
                event.product_id,
            )

    async def delete_sku(self, *, sku_id: UUID, seller_id: UUID) -> None:
        sku = await self._session.get(SKU, sku_id)
        if sku is None:
            raise SkuNotFoundError(f"SKU {sku_id} not found")

        product = await self._session.get(Product, sku.product_id)
        if product is None or product.seller_id != seller_id:
            raise ProductAccessDeniedError(
                f"SKU {sku_id} does not belong to the authenticated seller"
            )

        if product.status == ProductStatus.HARD_BLOCKED:
            raise ProductHardBlockedError("Cannot delete SKU of hard-blocked product")

        if sku.reserved_quantity > 0:
            raise SkuHasActiveReservesError("Cannot delete SKU with active reserves")

        saved_active_quantity = sku.active_quantity
        saved_product_status = product.status
        product_id = sku.product_id

        await self._session.delete(sku)
        await self._session.flush()

        is_last_sku = not await self._has_skus(product_id)

        outbox_event: OutboxEvent | None = None
        if is_last_sku and saved_product_status == ProductStatus.ON_MODERATION:
            product.status = ProductStatus.CREATED
            outbox_event = OutboxEvent(
                idempotency_key=uuid4(),
                product_id=product_id,
                seller_id=seller_id,
                event_type="DELETED",
            )
            self._session.add(outbox_event)

        await self._session.commit()

        if outbox_event is not None:
            await self._dispatch_outbox(outbox_event)

        if saved_active_quantity > 0 and saved_product_status == ProductStatus.MODERATED:
            await self._b2c_client.send_sku_out_of_stock(
                sku_id=sku_id,
                product_id=product_id,
                available_quantity=0,
            )

    async def _has_skus(self, product_id: UUID) -> bool:
        stmt = select(func.count()).select_from(SKU).where(SKU.product_id == product_id)
        count = int((await self._session.execute(stmt)).scalar() or 0)
        return count > 0
