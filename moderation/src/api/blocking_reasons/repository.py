from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.blocking_reasons.domain import (
    BlockingReasonDTO,
    ReasonCodeExistsError,
    ReasonNotFoundError,
)
from models import BlockingReason


def _to_dto(row: BlockingReason) -> BlockingReasonDTO:
    return BlockingReasonDTO(
        id=row.id,
        code=row.code,
        title=row.title,
        description=row.description,
        hard_block=bool(row.hard_block),
        is_active=bool(row.is_active),
    )


class BlockingReasonsRepositoryProtocol(Protocol):
    async def list_reasons(
        self, *, hard_block: bool | None, is_active: bool | None
    ) -> list[BlockingReasonDTO]: ...

    async def create(
        self, *, code: str, title: str, description: str | None, hard_block: bool
    ) -> BlockingReasonDTO: ...

    async def update(
        self,
        reason_id: UUID,
        *,
        title: str | None,
        description: str | None,
        is_active: bool | None,
    ) -> BlockingReasonDTO: ...

    async def deactivate(self, reason_id: UUID) -> None: ...


class InMemoryBlockingReasonsRepository:
    """In-process repository for tests."""

    def __init__(self) -> None:
        self._items: dict[UUID, BlockingReasonDTO] = {}

    def seed(self, *items: BlockingReasonDTO) -> None:
        for item in items:
            self._items[item.id] = item

    async def list_reasons(
        self, *, hard_block: bool | None, is_active: bool | None
    ) -> list[BlockingReasonDTO]:
        result = list(self._items.values())
        if is_active is not None:
            result = [r for r in result if r.is_active == is_active]
        if hard_block is not None:
            result = [r for r in result if r.hard_block == hard_block]
        return result

    async def create(
        self, *, code: str, title: str, description: str | None, hard_block: bool
    ) -> BlockingReasonDTO:
        if any(r.code == code for r in self._items.values()):
            raise ReasonCodeExistsError(code)
        dto = BlockingReasonDTO(
            id=uuid4(),
            code=code,
            title=title,
            description=description,
            hard_block=hard_block,
            is_active=True,
        )
        self._items[dto.id] = dto
        return dto

    async def update(
        self,
        reason_id: UUID,
        *,
        title: str | None,
        description: str | None,
        is_active: bool | None,
    ) -> BlockingReasonDTO:
        dto = self._items.get(reason_id)
        if dto is None:
            raise ReasonNotFoundError(str(reason_id))
        if title is not None:
            dto.title = title
        if description is not None:
            dto.description = description
        if is_active is not None:
            dto.is_active = is_active
        return dto

    async def deactivate(self, reason_id: UUID) -> None:
        dto = self._items.get(reason_id)
        if dto is None:
            raise ReasonNotFoundError(str(reason_id))
        # Soft delete only — the row is kept so historical BLOCKED cards keep their FK.
        dto.is_active = False


class DbBlockingReasonsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_reasons(
        self, *, hard_block: bool | None, is_active: bool | None
    ) -> list[BlockingReasonDTO]:
        stmt = select(BlockingReason)
        if is_active is not None:
            stmt = stmt.where(BlockingReason.is_active == is_active)
        if hard_block is not None:
            stmt = stmt.where(BlockingReason.hard_block == hard_block)
        stmt = stmt.order_by(BlockingReason.code)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_dto(row) for row in rows]

    async def create(
        self, *, code: str, title: str, description: str | None, hard_block: bool
    ) -> BlockingReasonDTO:
        existing = (
            await self._session.execute(
                select(BlockingReason).where(BlockingReason.code == code)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ReasonCodeExistsError(code)
        row = BlockingReason(
            code=code, title=title, description=description, hard_block=hard_block, is_active=True
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _to_dto(row)

    async def update(
        self,
        reason_id: UUID,
        *,
        title: str | None,
        description: str | None,
        is_active: bool | None,
    ) -> BlockingReasonDTO:
        row = await self._session.get(BlockingReason, reason_id)
        if row is None:
            raise ReasonNotFoundError(str(reason_id))
        if title is not None:
            row.title = title
        if description is not None:
            row.description = description
        if is_active is not None:
            row.is_active = is_active
        await self._session.commit()
        await self._session.refresh(row)
        return _to_dto(row)

    async def deactivate(self, reason_id: UUID) -> None:
        row = await self._session.get(BlockingReason, reason_id)
        if row is None:
            raise ReasonNotFoundError(str(reason_id))
        # Soft delete only — never physically remove, so FK references stay intact.
        row.is_active = False
        await self._session.commit()
