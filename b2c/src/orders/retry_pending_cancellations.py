from __future__ import annotations

import asyncio
import logging
import os
from uuid import UUID

from celery import Celery
from src.orders.domain import OrderStatus, ReserveRequestItem
from src.orders.repository import (
    HttpCheckoutCatalogClient,
    SqlAlchemyOrdersRepository,
    UpstreamServiceError,
)

logger = logging.getLogger(__name__)

celery_app = Celery(
    "b2c_orders",
    broker=os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/1")),
    backend=os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://localhost:6379/1")),
)


async def retry_pending_cancellations_once(
    repository: SqlAlchemyOrdersRepository,
    catalog_client: HttpCheckoutCatalogClient,
    batch_size: int = 100,
) -> None:
    pending_orders = await repository.list_by_status(
        status=OrderStatus.CANCEL_PENDING.value,
        limit=batch_size,
        offset=0,
    )
    for order in pending_orders:
        try:
            await catalog_client.unreserve(
                order_id=order.id,
                items=[
                    ReserveRequestItem(sku_id=item.sku_id, quantity=item.quantity)
                    for item in order.items
                ],
            )
        except UpstreamServiceError:
            logger.exception("Retry unreserve failed for order %s", order.id)
            raise

        updated_order = await repository.update_status(
            order_id=order.id,
            status=OrderStatus.CANCELLED.value,
        )
        if updated_order is None:
            logger.warning("Order %s disappeared before marking as CANCELLED", order.id)


async def retry_fulfill_order_once(
    repository: SqlAlchemyOrdersRepository,
    catalog_client: HttpCheckoutCatalogClient,
    order_id: UUID,
) -> None:
    order = await repository.get_by_id(order_id)
    if order is None:
        logger.warning("Order %s disappeared before fulfill retry", order_id)
        return

    if order.status != OrderStatus.DELIVERED:
        logger.info(
            "Skipping fulfill retry for order %s in status %s",
            order.id,
            order.status.value,
        )
        return

    await catalog_client.fulfill(
        order_id=order.id,
        items=[
            ReserveRequestItem(sku_id=item.sku_id, quantity=item.quantity) for item in order.items
        ],
    )


async def _retry_pending_cancellations_job(batch_size: int = 100) -> None:
    from src.orders.db import SessionLocal

    async with SessionLocal() as session:
        repository = SqlAlchemyOrdersRepository(session)
        catalog_client = HttpCheckoutCatalogClient()
        await retry_pending_cancellations_once(
            repository=repository,
            catalog_client=catalog_client,
            batch_size=batch_size,
        )


async def _retry_fulfill_order_job(order_id: str) -> None:
    from src.orders.db import SessionLocal

    async with SessionLocal() as session:
        repository = SqlAlchemyOrdersRepository(session)
        catalog_client = HttpCheckoutCatalogClient()
        await retry_fulfill_order_once(
            repository=repository,
            catalog_client=catalog_client,
            order_id=UUID(order_id),
        )


@celery_app.task(
    bind=True,
    autoretry_for=(UpstreamServiceError,),
    retry_backoff=True,
    retry_backoff_max=60 * 60,
    retry_jitter=True,
)
def retry_pending_cancellations_task(self, batch_size: int = 100) -> None:
    del self
    asyncio.run(_retry_pending_cancellations_job(batch_size=batch_size))


@celery_app.task(
    bind=True,
    autoretry_for=(UpstreamServiceError,),
    retry_backoff=True,
    retry_backoff_max=60 * 60,
    retry_jitter=True,
)
def retry_fulfill_order_task(self, order_id: str) -> None:
    del self
    asyncio.run(_retry_fulfill_order_job(order_id=order_id))


if __name__ == "__main__":
    asyncio.run(_retry_pending_cancellations_job())
