from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.banners.domain import Banner

if TYPE_CHECKING:
    from src.models import Banner as BannerModel


def _to_domain(row: BannerModel) -> Banner:
    return Banner(
        id=row.id,
        title=row.title,
        image_url=row.image_url,
        link=row.link,
        ordering=row.ordering,
        active_from=row.active_from,
        active_to=row.active_to,
        is_active=row.is_active,
    )


def _is_active_at(banner: Banner, now: datetime) -> bool:
    return (
        banner.is_active
        and (banner.active_from is None or banner.active_from <= now)
        and (banner.active_to is None or banner.active_to >= now)
    )


class BannerRepository(Protocol):
    async def list_active(self, *, now: datetime | None = None) -> list[Banner]: ...


class InMemoryBannerRepository:
    def __init__(self, banners: list[Banner] | None = None) -> None:
        self._banners = list(banners) if banners is not None else []

    async def list_active(self, *, now: datetime | None = None) -> list[Banner]:
        current_time = now or datetime.now(UTC)
        return sorted(
            (banner for banner in self._banners if _is_active_at(banner, current_time)),
            key=lambda banner: (banner.ordering, banner.title or "", str(banner.id)),
        )


class DbBannerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self, *, now: datetime | None = None) -> list[Banner]:
        from src.models import Banner as BannerModel

        current_time = now or datetime.now(UTC)
        result = await self._session.execute(
            select(BannerModel)
            .where(BannerModel.is_active.is_(True))
            .where(or_(BannerModel.active_from.is_(None), BannerModel.active_from <= current_time))
            .where(or_(BannerModel.active_to.is_(None), BannerModel.active_to >= current_time))
            .order_by(BannerModel.ordering, BannerModel.title, BannerModel.id)
        )
        return [_to_domain(row) for row in result.scalars()]
