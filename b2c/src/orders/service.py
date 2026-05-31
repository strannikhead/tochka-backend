from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from uuid import UUID, uuid4

from src.orders.domain import (
    CatalogSkuSnapshot,
    CheckoutItemInput,
    CheckoutOrderInput,
    OrderItemSnapshot,
    OrderSnapshot,
    OrderStatus,
    ReserveFailedItem,
    ReserveRequestItem,
)
from src.orders.repository import CheckoutCatalogClient, OrdersRepository, UpstreamServiceError

logger = logging.getLogger(__name__)


class CheckoutError(RuntimeError):
    def __init__(self, message: str, code: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ReserveFailedError(CheckoutError):
    def __init__(self, failed_items: list[dict[str, object]]) -> None:
        super().__init__("Не удалось зарезервировать товары", "RESERVE_FAILED", 409)
        self.failed_items = failed_items


class B2BUnavailableError(CheckoutError):
    def __init__(self) -> None:
        super().__init__(
            "Сервис товаров временно недоступен, попробуйте позже", "B2B_UNAVAILABLE", 503
        )


class InvalidRequestError(CheckoutError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "INVALID_REQUEST", 400)


class InvalidQuantityError(CheckoutError):
    def __init__(self) -> None:
        super().__init__(
            "Количество должно быть не менее 1 для каждой позиции", "INVALID_QUANTITY", 422
        )


class CancelNotAllowedError(CheckoutError):
    def __init__(self, current_status: str) -> None:
        super().__init__(
            f"Отмена невозможна: заказ в статусе {current_status}",
            "CANCEL_NOT_ALLOWED",
            409,
        )
        self.current_status = current_status


class IdempotencyConflictError(CheckoutError):
    def __init__(self) -> None:
        super().__init__(
            "Idempotency key already used with different request", "IDEMPOTENCY_CONFLICT", 409
        )


class CheckoutService:
    def __init__(self, repository: OrdersRepository, catalog_client: CheckoutCatalogClient) -> None:
        self._repository = repository
        self._catalog_client = catalog_client
        self._lock_guard = asyncio.Lock()
        self._locks: dict[UUID, asyncio.Lock] = {}

    async def create_order(
        self, *, user_id: UUID, payload: CheckoutOrderInput
    ) -> tuple[OrderSnapshot, bool]:
        lock = await self._get_lock(payload.idempotency_key)
        async with lock:
            existing = await self._repository.get_by_idempotency_key(payload.idempotency_key)
            if existing is not None:
                if existing.request_fingerprint != payload.request_fingerprint:
                    raise IdempotencyConflictError()
                return existing, False

            if not payload.items:
                raise InvalidRequestError("Список items не может быть пустым")

            if any(item.quantity < 1 for item in payload.items):
                raise InvalidQuantityError()

            sku_ids = [item.sku_id for item in payload.items]
            order_id = uuid4()
            try:
                skus = await self._catalog_client.get_skus_by_ids(sku_ids)
            except UpstreamServiceError as exc:
                raise B2BUnavailableError() from exc

            by_id = {sku.sku_id: sku for sku in skus}
            failed_items = _validate_items(payload.items, by_id)
            if failed_items:
                raise ReserveFailedError(failed_items)

            try:
                reserve_result = await self._catalog_client.reserve(
                    order_id=order_id,
                    idempotency_key=payload.idempotency_key,
                    items=[
                        ReserveRequestItem(sku_id=item.sku_id, quantity=item.quantity)
                        for item in payload.items
                    ],
                )
            except UpstreamServiceError as exc:
                raise B2BUnavailableError() from exc

            if not reserve_result.reserved:
                raise ReserveFailedError(
                    [_failed_item_to_dict(item) for item in reserve_result.failed_items]
                )

            order_items = tuple(
                _build_order_item(sku=by_id[item.sku_id], item=item) for item in payload.items
            )
            order = OrderSnapshot.create(
                order_id=order_id,
                user_id=user_id,
                idempotency_key=payload.idempotency_key,
                address_id=payload.address_id,
                payment_method_id=payload.payment_method_id,
                request_fingerprint=payload.request_fingerprint,
                items=order_items,
            )
            await self._repository.save(order)
            return order, True

    async def cancel_order(self, *, user_id: UUID, order_id: UUID) -> OrderSnapshot | None:
        order = await self._repository.get_for_user(order_id=order_id, user_id=user_id)
        if order is None:
            return None

        if order.status not in {OrderStatus.CREATED, OrderStatus.PAID}:
            raise CancelNotAllowedError(order.status.value)

        try:
            await self._catalog_client.unreserve(
                order_id=order.id,
                items=[
                    ReserveRequestItem(sku_id=item.sku_id, quantity=item.quantity)
                    for item in order.items
                ],
            )
        except UpstreamServiceError as exc:
            logger.exception("Failed to unreserve order %s, marking as CANCEL_PENDING", order.id)
            pending_order = await self._repository.update_status_for_user(
                order_id=order.id,
                user_id=user_id,
                status=OrderStatus.CANCEL_PENDING.value,
            )
            if pending_order is None:
                raise RuntimeError("Order disappeared while marking CANCEL_PENDING") from exc
            return pending_order

        cancelled_order = await self._repository.update_status_for_user(
            order_id=order.id,
            user_id=user_id,
            status=OrderStatus.CANCELLED.value,
        )
        if cancelled_order is None:
            raise RuntimeError("Order disappeared while marking CANCELLED")
        return cancelled_order

    async def mark_order_delivered(self, *, order_id: UUID) -> OrderSnapshot | None:
        order = await self._repository.get_by_id(order_id)
        if order is None:
            return None

        updated_order = await self._repository.update_status(
            order_id=order.id,
            status=OrderStatus.DELIVERED.value,
        )
        if updated_order is None:
            raise RuntimeError("Order disappeared while marking DELIVERED")

        if order.status == OrderStatus.DELIVERED:
            return updated_order

        try:
            await self._fulfill_order(updated_order)
        except UpstreamServiceError:
            logger.exception(
                "Failed to fulfill delivered order %s, scheduling async retry",
                updated_order.id,
            )
            enqueue_fulfill_retry(updated_order.id)

        return updated_order

    async def _fulfill_order(self, order: OrderSnapshot) -> None:
        await self._catalog_client.fulfill(
            order_id=order.id,
            items=[
                ReserveRequestItem(sku_id=item.sku_id, quantity=item.quantity)
                for item in order.items
            ],
        )

    async def _get_lock(self, idempotency_key: UUID) -> asyncio.Lock:
        async with self._lock_guard:
            lock = self._locks.get(idempotency_key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[idempotency_key] = lock
            return lock


def enqueue_fulfill_retry(order_id: UUID) -> None:
    try:
        from src.orders.retry_pending_cancellations import retry_fulfill_order_task

        retry_fulfill_order_task.delay(str(order_id))
    except Exception:
        logger.exception("Failed to enqueue fulfill retry for order %s", order_id)


def _validate_items(
    items: Iterable[CheckoutItemInput],
    skus_by_id: dict[UUID, CatalogSkuSnapshot],
) -> list[dict[str, object]]:
    failed_items: list[dict[str, object]] = []
    for item in items:
        sku = skus_by_id.get(item.sku_id)
        if sku is None:
            failed_items.append(
                {
                    "sku_id": str(item.sku_id),
                    "requested": item.quantity,
                    "available": 0,
                    "reason": "SKU_NOT_FOUND",
                }
            )
            continue
        if sku.product_deleted:
            failed_items.append(
                {
                    "sku_id": str(item.sku_id),
                    "requested": item.quantity,
                    "available": sku.active_quantity,
                    "reason": "PRODUCT_DELETED",
                }
            )
            continue
        if sku.product_status != "MODERATED":
            failed_items.append(
                {
                    "sku_id": str(item.sku_id),
                    "requested": item.quantity,
                    "available": sku.active_quantity,
                    "reason": "PRODUCT_BLOCKED",
                }
            )
            continue
        if sku.active_quantity < item.quantity:
            failed_items.append(
                {
                    "sku_id": str(item.sku_id),
                    "requested": item.quantity,
                    "available": sku.active_quantity,
                    "reason": "INSUFFICIENT_STOCK" if sku.active_quantity > 0 else "OUT_OF_STOCK",
                }
            )
    return failed_items


def _build_order_item(*, sku: CatalogSkuSnapshot, item: CheckoutItemInput) -> OrderItemSnapshot:
    unit_price = sku.unit_price
    line_total = unit_price * item.quantity
    return OrderItemSnapshot(
        id=uuid4(),
        sku_id=item.sku_id,
        product_id=sku.product_id,
        product_title=sku.product_title,
        sku_name=sku.sku_name,
        quantity=item.quantity,
        unit_price=unit_price,
        line_total=line_total,
    )


def _failed_item_to_dict(item: ReserveFailedItem) -> dict[str, object]:
    return {
        "sku_id": str(item.sku_id),
        "requested": item.requested,
        "available": item.available,
        "reason": item.reason,
    }
