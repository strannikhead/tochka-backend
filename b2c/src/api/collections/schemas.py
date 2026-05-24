from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel
from src.collections.domain import B2BProductCard, B2BProductImage, CollectionEnriched


class ImageRefResponse(BaseModel):
    id: UUID
    url: str
    ordering: int
    is_main: bool

    @classmethod
    def from_domain(cls, image: B2BProductImage) -> ImageRefResponse:
        return cls(
            id=image.id,
            url=image.url,
            ordering=image.ordering,
            is_main=image.is_main,
        )


class CatalogProductCardResponse(BaseModel):
    id: UUID
    name: str
    slug: str | None = None
    min_price: int
    has_stock: bool
    images: list[ImageRefResponse]

    @classmethod
    def from_domain(cls, product: B2BProductCard) -> CatalogProductCardResponse:
        return cls(
            id=product.id,
            name=product.name,
            slug=product.slug,
            min_price=product.min_price,
            has_stock=product.has_stock,
            images=[ImageRefResponse.from_domain(img) for img in product.images],
        )


class CollectionResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    products: list[CatalogProductCardResponse]

    @classmethod
    def from_domain(cls, collection: CollectionEnriched) -> CollectionResponse:
        return cls(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            products=[CatalogProductCardResponse.from_domain(p) for p in collection.products],
        )
