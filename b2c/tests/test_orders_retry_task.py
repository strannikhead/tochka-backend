from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from src.orders.domain import OrderItemSnapshot, OrderSnapshot, OrderStatus
from src.orders.repository import UpstreamServiceError
from src.orders.retry_pending_cancellations import (
    retry_pending_cancellations_once,
    retry_pending_cancellations_task,
)

USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SKU_ID_1 = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")
SKU_ID_2 = UUID("8a4e3f9c-1a2b-4c8d-9e5f-6b7a8c9d0e1f")


def _make_order(order_id: UUID, sku_id: UUID) -> OrderSnapshot:
    now = datetime.now(UTC)
    item = OrderItemSnapshot(
        id=uuid4(),
        sku_id=sku_id,
        product_id=uuid4(),
        product_title="Test product",
        sku_name="Default SKU",
        quantity=1,
        unit_price=1000,
        line_total=1000,
    )
    return OrderSnapshot(
        id=order_id,
        user_id=USER_ID,
        idempotency_key=uuid4(),
        status=OrderStatus.CANCEL_PENDING,
        items=(item,),
        total_amount=1000,
        delivery_address=None,
        created_at=now,
        updated_at=now,
    )


class FakeRepository:
    def __init__(self, orders: list[OrderSnapshot]) -> None:
        self.orders = orders
        self.updated: list[tuple[UUID, str]] = []

    async def list_by_status(self, *, status: str, limit: int, offset: int = 0):
        assert status == OrderStatus.CANCEL_PENDING.value
        assert offset == 0
        return self.orders[:limit]

    async def update_status(self, *, order_id: UUID, status: str):
        self.updated.append((order_id, status))
        for order in self.orders:
            if order.id == order_id:
                return replace(order, status=OrderStatus(status), updated_at=datetime.now(UTC))
        return None


class FakeCatalogClient:
    def __init__(self, failing_order_id: UUID | None = None) -> None:
        self.failing_order_id = failing_order_id
        self.calls: list[tuple[UUID, tuple[tuple[UUID, int], ...]]] = []

    async def unreserve(self, *, order_id: UUID, items):
        self.calls.append(
            (
                order_id,
                tuple((item.sku_id, item.quantity) for item in items),
            )
        )
        if self.failing_order_id is not None and order_id == self.failing_order_id:
            raise UpstreamServiceError("B2B temporarily unavailable", None)


@pytest.mark.asyncio
async def test_retry_pending_cancellations_marks_all_orders_cancelled() -> None:
    first_order = _make_order(uuid4(), SKU_ID_1)
    second_order = _make_order(uuid4(), SKU_ID_2)
    repository = FakeRepository([first_order, second_order])
    catalog_client = FakeCatalogClient()

    await retry_pending_cancellations_once(repository, catalog_client, batch_size=10)

    assert catalog_client.calls[0][0] == first_order.id
    assert catalog_client.calls[1][0] == second_order.id
    assert repository.updated == [
        (first_order.id, "CANCELLED"),
        (second_order.id, "CANCELLED"),
    ]


@pytest.mark.asyncio
async def test_retry_pending_cancellations_propagates_unreserve_failure() -> None:
    first_order = _make_order(uuid4(), SKU_ID_1)
    failing_order = _make_order(uuid4(), SKU_ID_2)
    repository = FakeRepository([first_order, failing_order])
    catalog_client = FakeCatalogClient(failing_order_id=failing_order.id)

    with pytest.raises(UpstreamServiceError):
        await retry_pending_cancellations_once(repository, catalog_client, batch_size=10)

    assert repository.updated == [(first_order.id, "CANCELLED")]
    assert catalog_client.calls[0][0] == first_order.id
    assert catalog_client.calls[1][0] == failing_order.id


def test_celery_task_uses_exponential_backoff() -> None:
    assert retry_pending_cancellations_task.autoretry_for == (UpstreamServiceError,)
    assert retry_pending_cancellations_task.retry_backoff is True
    assert retry_pending_cancellations_task.retry_backoff_max == 60 * 60
    assert retry_pending_cancellations_task.retry_jitter is True
