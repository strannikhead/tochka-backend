from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from b2c.src.catalog.domain import ProductShort, ProductShortList
from b2c.src.product_card.domain import Characteristic, Image, Product, Sku


class ImageRefResponse(BaseModel):
    id: UUID
    url: str
    ordering: int

    @classmethod
    def from_domain(cls, image: Image) -> ImageRefResponse:
        return cls(id=image.id, url=image.url, ordering=image.ordering)


class CharacteristicResponse(BaseModel):
    name: str
    value: str

    @classmethod
    def from_domain(cls, characteristic: Characteristic) -> CharacteristicResponse:
        return cls(name=characteristic.name, value=characteristic.value)


class CatalogSkuResponse(BaseModel):
    id: UUID
    price: int
    available_quantity: int
    name: str | None = None
    sku_code: str | None = None
    old_price: int | None = None
    attributes: dict[str, Any] | None = None
    images: list[ImageRefResponse]

    @classmethod
    def from_domain(cls, sku: Sku) -> CatalogSkuResponse:
        attributes = {item.name: item.value for item in sku.characteristics}
        discounted_price = sku.price - sku.discount
        old_price = sku.price if sku.discount > 0 else None
        return cls(
            id=sku.id,
            name=sku.name or None,
            sku_code=sku.sku_code,
            price=discounted_price,
            old_price=old_price,
            available_quantity=sku.available_quantity,
            attributes=attributes or None,
            images=[ImageRefResponse.from_domain(image) for image in sku.images],
        )


class CatalogProductCardResponse(BaseModel):
    id: UUID
    name: str
    min_price: int
    has_stock: bool
    images: list[ImageRefResponse]
    slug: str | None = None
    old_price: int | None = None
    rating: float | None = None
    reviews_count: int | None = None

    @classmethod
    def from_domain(cls, product: Product) -> CatalogProductCardResponse:
        sku_prices = [sku.price - sku.discount for sku in product.skus]
        min_price = min(sku_prices) if sku_prices else product.min_price or 0
        has_stock = any(sku.available_quantity > 0 for sku in product.skus)
        if not product.skus:
            has_stock = bool(min_price)
        old_price = None
        if product.skus:
            candidate = min(product.skus, key=lambda sku: sku.price - sku.discount)
            old_price = candidate.price if candidate.discount > 0 else None
        return cls(
            id=product.id,
            name=product.name,
            slug=product.slug or None,
            min_price=min_price,
            old_price=old_price,
            has_stock=has_stock,
            images=[ImageRefResponse.from_domain(image) for image in product.images],
        )


class CatalogProductDetailResponse(CatalogProductCardResponse):
    description: str
    attributes: dict[str, Any] | None = None
    skus: list[CatalogSkuResponse]

    @classmethod
    def from_domain(cls, product: Product) -> CatalogProductDetailResponse:
        attributes = {item.name: item.value for item in product.characteristics}
        card = CatalogProductCardResponse.from_domain(product)
        return cls(
            **card.model_dump(),
            description=product.description,
            attributes=attributes or None,
            skus=[CatalogSkuResponse.from_domain(sku) for sku in product.skus],
        )


class ProductShortResponse(BaseModel):
    id: UUID
    title: str
    image: str
    price: int
    in_stock: bool
    is_in_cart: bool

    @classmethod
    def from_domain(cls, product: ProductShort) -> ProductShortResponse:
        return cls(
            id=product.id,
            title=product.title,
            image=product.image,
            price=product.price,
            in_stock=product.in_stock,
            is_in_cart=product.is_in_cart,
        )


class ProductShortListResponse(BaseModel):
    total_count: int
    limit: int
    offset: int
    items: list[ProductShortResponse]

    @classmethod
    def from_domain(cls, product_list: ProductShortList) -> ProductShortListResponse:
        return cls(
            total_count=product_list.total_count,
            limit=product_list.limit,
            offset=product_list.offset,
            items=[ProductShortResponse.from_domain(item) for item in product_list.items],
        )


class PaginatedCatalogProductsResponse(BaseModel):
    items: list[CatalogProductCardResponse]
    total_count: int
    limit: int
    offset: int
