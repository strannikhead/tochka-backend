from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from src.orders.domain import OrderItemSnapshot, OrderSnapshot, OrderStatus
from src.orders.repository import UpstreamServiceError
from src.orders.retry_pending_cancellations import retry_fulfill_order_once
from src.orders.service import CheckoutService

USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SKU_ID = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")


def _make_order(
    *, status: OrderStatus = OrderStatus.DELIVERING, quantity: int = 2
) -> OrderSnapshot:
    now = datetime.now(UTC)
    item = OrderItemSnapshot(
        id=uuid4(),
        sku_id=SKU_ID,
        product_id=uuid4(),
        product_title="Test product",
        sku_name="Default SKU",
        quantity=quantity,
        unit_price=1000,
        line_total=1000 * quantity,
    )
    return OrderSnapshot(
        id=uuid4(),
        user_id=USER_ID,
        idempotency_key=uuid4(),
        address_id=uuid4(),
        payment_method_id=uuid4(),
        request_fingerprint="fingerprint",
        status=status,
        items=(item,),
        total_amount=1000 * quantity,
        created_at=now,
        updated_at=now,
    )


class FakeRepository:
    def __init__(self, order: OrderSnapshot) -> None:
        self.order = order
        self.updated: list[tuple[UUID, str]] = []

    async def get_by_id(self, order_id: UUID) -> OrderSnapshot | None:
        if self.order.id == order_id:
            return self.order
        return None

    async def update_status(self, *, order_id: UUID, status: str) -> OrderSnapshot | None:
        if self.order.id != order_id:
            return None
        self.updated.append((order_id, status))
        self.order = replace(self.order, status=OrderStatus(status), updated_at=datetime.now(UTC))
        return self.order


class FakeCatalogClient:
    def __init__(self, *, fail_fulfill: bool = False) -> None:
        self.fail_fulfill = fail_fulfill
        self.fulfill_calls: list[tuple[UUID, tuple[tuple[UUID, int], ...]]] = []

    async def fulfill(self, *, order_id: UUID, items) -> None:
        self.fulfill_calls.append(
            (
                order_id,
                tuple((item.sku_id, item.quantity) for item in items),
            )
        )
        if self.fail_fulfill:
            raise UpstreamServiceError("B2B temporarily unavailable", None)


class IdempotentFulfillCatalogClient:
    def __init__(self, *, reserved_quantity: int) -> None:
        self.reserved_quantity = reserved_quantity
        self.fulfilled_orders: set[UUID] = set()
        self.calls: list[UUID] = []

    async def fulfill(self, *, order_id: UUID, items) -> None:
        self.calls.append(order_id)
        if order_id in self.fulfilled_orders:
            return
        for item in items:
            self.reserved_quantity -= item.quantity
        self.fulfilled_orders.add(order_id)


@pytest.mark.asyncio
async def test_delivered_status_triggers_fulfill_to_b2b() -> None:
    order = _make_order(status=OrderStatus.DELIVERING, quantity=2)
    repository = FakeRepository(order)
    catalog_client = FakeCatalogClient()
    service = CheckoutService(repository, catalog_client)

    delivered = await service.mark_order_delivered(order_id=order.id)

    assert delivered is not None
    assert delivered.status == OrderStatus.DELIVERED
    assert repository.updated == [(order.id, OrderStatus.DELIVERED.value)]
    assert catalog_client.fulfill_calls == [(order.id, ((SKU_ID, 2),))]


@pytest.mark.asyncio
async def test_fulfill_failure_retried_asynchronously(monkeypatch: pytest.MonkeyPatch) -> None:
    order = _make_order(status=OrderStatus.DELIVERING, quantity=2)
    repository = FakeRepository(order)
    catalog_client = FakeCatalogClient(fail_fulfill=True)
    service = CheckoutService(repository, catalog_client)
    enqueued: list[UUID] = []

    monkeypatch.setattr("src.orders.service.enqueue_fulfill_retry", enqueued.append)

    delivered = await service.mark_order_delivered(order_id=order.id)

    assert delivered is not None
    assert delivered.status == OrderStatus.DELIVERED
    assert repository.updated == [(order.id, OrderStatus.DELIVERED.value)]
    assert catalog_client.fulfill_calls == [(order.id, ((SKU_ID, 2),))]
    assert enqueued == [order.id]


@pytest.mark.asyncio
async def test_repeated_fulfill_idempotent() -> None:
    order = _make_order(status=OrderStatus.DELIVERED, quantity=2)
    repository = FakeRepository(order)
    catalog_client = IdempotentFulfillCatalogClient(reserved_quantity=5)

    await retry_fulfill_order_once(repository, catalog_client, order.id)
    await retry_fulfill_order_once(repository, catalog_client, order.id)

    assert catalog_client.calls == [order.id, order.id]
    assert catalog_client.reserved_quantity == 3
