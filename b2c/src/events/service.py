from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from src.cart.repository import CartRepository
from src.events.repository import EventIdempotencyRepository
from src.events.schemas import ProductEventType


@dataclass(frozen=True)
class ProductEventCommand:
    idempotency_key: UUID
    event_type: ProductEventType
    sku_ids: tuple[UUID, ...]


class ProductEventService:
    def __init__(
        self,
        cart_repository: CartRepository,
        idempotency_repository: EventIdempotencyRepository,
    ) -> None:
        self._cart_repository = cart_repository
        self._idempotency_repository = idempotency_repository
        self._lock_guard = asyncio.Lock()
        self._locks: dict[UUID, asyncio.Lock] = {}

    async def handle(self, command: ProductEventCommand) -> bool:
        lock = await self._get_lock(command.idempotency_key)
        async with lock:
            if await self._idempotency_repository.was_processed(command.idempotency_key):
                return False

            reason = _reason_for(command.event_type)
            if reason is not None or command.event_type == ProductEventType.SKU_BACK_IN_STOCK:
                await self._cart_repository.mark_items_unavailable_by_sku_ids(
                    sku_ids=list(dict.fromkeys(command.sku_ids)),
                    unavailable_reason=reason,
                )

            await self._idempotency_repository.mark_processed(
                idempotency_key=command.idempotency_key,
                event_type=command.event_type.value,
            )
            return True

    async def _get_lock(self, idempotency_key: UUID) -> asyncio.Lock:
        async with self._lock_guard:
            lock = self._locks.get(idempotency_key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[idempotency_key] = lock
            return lock


def _reason_for(event_type: ProductEventType) -> str | None:
    if event_type in (ProductEventType.PRODUCT_BLOCKED, ProductEventType.PRODUCT_HARD_BLOCKED):
        return "PRODUCT_BLOCKED"
    if event_type == ProductEventType.PRODUCT_DELETED:
        return "PRODUCT_DELETED"
    if event_type == ProductEventType.SKU_OUT_OF_STOCK:
        return "OUT_OF_STOCK"
    return None
