from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.cart.domain import CartItemStored

if TYPE_CHECKING:
    from src.models import CartItem as CartItemModel


def _to_domain(row: CartItemModel) -> CartItemStored:
    return CartItemStored(
        id=row.id,
        user_id=row.user_id,
        session_id=row.session_id,
        sku_id=row.sku_id,
        quantity=row.quantity,
        added_at=row.added_at,
        updated_at=row.updated_at,
    )


class CartRepository(Protocol):
    async def get_items(
        self, *, user_id: uuid.UUID | None, session_id: str | None
    ) -> list[CartItemStored]: ...

    async def get_item(
        self, *, item_id: uuid.UUID, user_id: uuid.UUID | None, session_id: str | None
    ) -> CartItemStored | None: ...

    async def upsert_item(
        self,
        *,
        user_id: uuid.UUID | None,
        session_id: str | None,
        sku_id: uuid.UUID,
        quantity: int,
    ) -> tuple[CartItemStored, bool]: ...

    async def set_item_quantity(
        self,
        *,
        item_id: uuid.UUID,
        user_id: uuid.UUID | None,
        session_id: str | None,
        quantity: int,
    ) -> CartItemStored | None: ...

    async def set_item_quantity_by_sku(
        self,
        *,
        sku_id: uuid.UUID,
        user_id: uuid.UUID | None,
        session_id: str | None,
        quantity: int,
    ) -> CartItemStored | None: ...

    async def delete_item(
        self, *, item_id: uuid.UUID, user_id: uuid.UUID | None, session_id: str | None
    ) -> bool: ...

    async def delete_item_by_sku(
        self, *, sku_id: uuid.UUID, user_id: uuid.UUID | None, session_id: str | None
    ) -> bool: ...

    async def clear(self, *, user_id: uuid.UUID | None, session_id: str | None) -> None: ...

    async def merge_guest_into_user(self, *, session_id: str, user_id: uuid.UUID) -> None: ...


class InMemoryCartRepository:
    def __init__(self, items: dict[uuid.UUID, CartItemStored] | None = None) -> None:
        self._items: dict[uuid.UUID, CartItemStored] = items if items is not None else {}

    def _matches(
        self, item: CartItemStored, user_id: uuid.UUID | None, session_id: str | None
    ) -> bool:
        if user_id is not None:
            return item.user_id == user_id
        return item.session_id == session_id

    async def get_items(
        self, *, user_id: uuid.UUID | None, session_id: str | None
    ) -> list[CartItemStored]:
        return [item for item in self._items.values() if self._matches(item, user_id, session_id)]

    async def get_item(
        self, *, item_id: uuid.UUID, user_id: uuid.UUID | None, session_id: str | None
    ) -> CartItemStored | None:
        item = self._items.get(item_id)
        if item is None or not self._matches(item, user_id, session_id):
            return None
        return item

    async def upsert_item(
        self,
        *,
        user_id: uuid.UUID | None,
        session_id: str | None,
        sku_id: uuid.UUID,
        quantity: int,
    ) -> tuple[CartItemStored, bool]:
        existing = next(
            (
                item
                for item in self._items.values()
                if self._matches(item, user_id, session_id) and item.sku_id == sku_id
            ),
            None,
        )
        now = datetime.now(UTC)
        if existing is not None:
            updated = CartItemStored(
                id=existing.id,
                user_id=existing.user_id,
                session_id=existing.session_id,
                sku_id=existing.sku_id,
                quantity=existing.quantity + quantity,
                added_at=existing.added_at,
                updated_at=now,
            )
            self._items[updated.id] = updated
            return updated, False

        new_item = CartItemStored(
            id=uuid.uuid4(),
            user_id=user_id,
            session_id=session_id,
            sku_id=sku_id,
            quantity=quantity,
            added_at=now,
            updated_at=now,
        )
        self._items[new_item.id] = new_item
        return new_item, True

    async def set_item_quantity(
        self,
        *,
        item_id: uuid.UUID,
        user_id: uuid.UUID | None,
        session_id: str | None,
        quantity: int,
    ) -> CartItemStored | None:
        item = self._items.get(item_id)
        if item is None or not self._matches(item, user_id, session_id):
            return None
        updated = CartItemStored(
            id=item.id,
            user_id=item.user_id,
            session_id=item.session_id,
            sku_id=item.sku_id,
            quantity=quantity,
            added_at=item.added_at,
            updated_at=datetime.now(UTC),
        )
        self._items[updated.id] = updated
        return updated

    async def set_item_quantity_by_sku(
        self,
        *,
        sku_id: uuid.UUID,
        user_id: uuid.UUID | None,
        session_id: str | None,
        quantity: int,
    ) -> CartItemStored | None:
        item = next(
            (
                i
                for i in self._items.values()
                if self._matches(i, user_id, session_id) and i.sku_id == sku_id
            ),
            None,
        )
        if item is None:
            return None
        return await self.set_item_quantity(
            item_id=item.id, user_id=user_id, session_id=session_id, quantity=quantity
        )

    async def delete_item(
        self, *, item_id: uuid.UUID, user_id: uuid.UUID | None, session_id: str | None
    ) -> bool:
        item = self._items.get(item_id)
        if item is None or not self._matches(item, user_id, session_id):
            return False
        del self._items[item_id]
        return True

    async def delete_item_by_sku(
        self, *, sku_id: uuid.UUID, user_id: uuid.UUID | None, session_id: str | None
    ) -> bool:
        item = next(
            (
                i
                for i in self._items.values()
                if self._matches(i, user_id, session_id) and i.sku_id == sku_id
            ),
            None,
        )
        if item is None:
            return False
        del self._items[item.id]
        return True

    async def clear(self, *, user_id: uuid.UUID | None, session_id: str | None) -> None:
        to_delete = [
            item_id
            for item_id, item in self._items.items()
            if self._matches(item, user_id, session_id)
        ]
        for item_id in to_delete:
            del self._items[item_id]

    async def merge_guest_into_user(self, *, session_id: str, user_id: uuid.UUID) -> None:
        guest_items = [item for item in self._items.values() if item.session_id == session_id]
        now = datetime.now(UTC)
        for guest_item in guest_items:
            user_item = next(
                (
                    item
                    for item in self._items.values()
                    if item.user_id == user_id and item.sku_id == guest_item.sku_id
                ),
                None,
            )
            if user_item is not None:
                merged = CartItemStored(
                    id=user_item.id,
                    user_id=user_item.user_id,
                    session_id=None,
                    sku_id=user_item.sku_id,
                    quantity=max(user_item.quantity, guest_item.quantity),
                    added_at=user_item.added_at,
                    updated_at=now,
                )
                self._items[user_item.id] = merged
            else:
                transferred = CartItemStored(
                    id=guest_item.id,
                    user_id=user_id,
                    session_id=None,
                    sku_id=guest_item.sku_id,
                    quantity=guest_item.quantity,
                    added_at=guest_item.added_at,
                    updated_at=now,
                )
                self._items[transferred.id] = transferred

        to_delete = [
            item_id for item_id, item in self._items.items() if item.session_id == session_id
        ]
        for item_id in to_delete:
            del self._items[item_id]


class DbCartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _owner_clause(self, user_id: uuid.UUID | None, session_id: str | None):
        from src.models import CartItem

        if user_id is not None:
            return CartItem.user_id == user_id
        return CartItem.session_id == session_id

    async def get_items(
        self, *, user_id: uuid.UUID | None, session_id: str | None
    ) -> list[CartItemStored]:
        from src.models import CartItem

        result = await self._session.execute(
            select(CartItem).where(self._owner_clause(user_id, session_id))
        )
        return [_to_domain(row) for row in result.scalars()]

    async def get_item(
        self, *, item_id: uuid.UUID, user_id: uuid.UUID | None, session_id: str | None
    ) -> CartItemStored | None:
        from src.models import CartItem

        result = await self._session.execute(
            select(CartItem).where(
                CartItem.id == item_id,
                self._owner_clause(user_id, session_id),
            )
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def upsert_item(
        self,
        *,
        user_id: uuid.UUID | None,
        session_id: str | None,
        sku_id: uuid.UUID,
        quantity: int,
    ) -> tuple[CartItemStored, bool]:
        from src.models import CartItem

        result = await self._session.execute(
            select(CartItem).where(
                self._owner_clause(user_id, session_id),
                CartItem.sku_id == sku_id,
            )
        )
        existing = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if existing is not None:
            existing.quantity += quantity
            existing.updated_at = now
            await self._session.commit()
            return _to_domain(existing), False

        new_item = CartItem(
            id=uuid.uuid4(),
            user_id=user_id,
            session_id=session_id,
            sku_id=sku_id,
            quantity=quantity,
            added_at=now,
            updated_at=now,
        )
        self._session.add(new_item)
        await self._session.commit()
        return _to_domain(new_item), True

    async def set_item_quantity(
        self,
        *,
        item_id: uuid.UUID,
        user_id: uuid.UUID | None,
        session_id: str | None,
        quantity: int,
    ) -> CartItemStored | None:
        from src.models import CartItem

        result = await self._session.execute(
            select(CartItem).where(
                CartItem.id == item_id,
                self._owner_clause(user_id, session_id),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None
        item.quantity = quantity
        item.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _to_domain(item)

    async def set_item_quantity_by_sku(
        self,
        *,
        sku_id: uuid.UUID,
        user_id: uuid.UUID | None,
        session_id: str | None,
        quantity: int,
    ) -> CartItemStored | None:
        from src.models import CartItem

        result = await self._session.execute(
            select(CartItem).where(
                self._owner_clause(user_id, session_id),
                CartItem.sku_id == sku_id,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None
        item.quantity = quantity
        item.updated_at = datetime.now(UTC)
        await self._session.commit()
        return _to_domain(item)

    async def delete_item(
        self, *, item_id: uuid.UUID, user_id: uuid.UUID | None, session_id: str | None
    ) -> bool:
        from src.models import CartItem

        result = await self._session.execute(
            select(CartItem).where(
                CartItem.id == item_id,
                self._owner_clause(user_id, session_id),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return False
        await self._session.delete(item)
        await self._session.commit()
        return True

    async def delete_item_by_sku(
        self, *, sku_id: uuid.UUID, user_id: uuid.UUID | None, session_id: str | None
    ) -> bool:
        from src.models import CartItem

        result = await self._session.execute(
            select(CartItem).where(
                self._owner_clause(user_id, session_id),
                CartItem.sku_id == sku_id,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return False
        await self._session.delete(item)
        await self._session.commit()
        return True

    async def clear(self, *, user_id: uuid.UUID | None, session_id: str | None) -> None:
        from src.models import CartItem

        await self._session.execute(delete(CartItem).where(self._owner_clause(user_id, session_id)))
        await self._session.commit()

    async def merge_guest_into_user(self, *, session_id: str, user_id: uuid.UUID) -> None:
        from src.models import CartItem

        guest_result = await self._session.execute(
            select(CartItem).where(CartItem.session_id == session_id)
        )
        guest_items = guest_result.scalars().all()

        now = datetime.now(UTC)
        for guest_item in guest_items:
            user_result = await self._session.execute(
                select(CartItem).where(
                    CartItem.user_id == user_id,
                    CartItem.sku_id == guest_item.sku_id,
                )
            )
            user_item = user_result.scalar_one_or_none()
            if user_item is not None:
                user_item.quantity = max(user_item.quantity, guest_item.quantity)
                user_item.updated_at = now
                await self._session.delete(guest_item)
            else:
                guest_item.user_id = user_id
                guest_item.session_id = None
                guest_item.updated_at = now

        await self._session.commit()
