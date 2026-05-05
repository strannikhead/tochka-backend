from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel
from src.catalog.domain import Facet, Facets, FacetValue


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
