from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from src.banners.domain import Banner

from b2c.src.catalog.domain import Facet, Facets, FacetValue


class FacetValueResponse(BaseModel):
    value: str
    count: int

    @classmethod
    def from_domain(cls, value: FacetValue) -> FacetValueResponse:
        return cls(value=value.value, count=value.count)


class FacetResponse(BaseModel):
    name: str
    values: list[FacetValueResponse]

    @classmethod
    def from_domain(cls, facet: Facet) -> FacetResponse:
        return cls(
            name=facet.name,
            values=[FacetValueResponse.from_domain(value) for value in facet.values],
        )


class FacetsResponse(BaseModel):
    category_id: UUID
    facets: list[FacetResponse]

    @classmethod
    def from_domain(cls, facets: Facets) -> FacetsResponse:
        return cls(
            category_id=facets.category_id,
            facets=[FacetResponse.from_domain(facet) for facet in facets.facets],
        )


class BannerResponse(BaseModel):
    id: UUID
    title: str | None = None
    image_url: str
    link: str
    ordering: int
    active_from: datetime | None = None
    active_to: datetime | None = None

    @classmethod
    def from_domain(cls, banner: Banner) -> BannerResponse:
        return cls(
            id=banner.id,
            title=banner.title,
            image_url=banner.image_url,
            link=banner.link,
            ordering=banner.ordering,
            active_from=banner.active_from,
            active_to=banner.active_to,
        )
