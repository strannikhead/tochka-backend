from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from product_card.domain import Characteristic, Image, Product, ProductStatus, Sku


class ImageResponse(BaseModel):
    url: str
    order: int

    @classmethod
    def from_domain(cls, image: Image) -> ImageResponse:
        return cls(url=image.url, order=image.order)


class CharacteristicResponse(BaseModel):
    name: str
    value: str

    @classmethod
    def from_domain(cls, characteristic: Characteristic) -> CharacteristicResponse:
        return cls(name=characteristic.name, value=characteristic.value)


class SkuResponse(BaseModel):
    id: UUID
    name: str
    price: int
    discount: int
    quantity: int
    in_stock: bool
    characteristics: list[CharacteristicResponse]
    images: list[ImageResponse]

    @classmethod
    def from_domain(cls, sku: Sku) -> SkuResponse:
        return cls(
            id=sku.id,
            name=sku.name,
            price=sku.price,
            discount=sku.discount,
            quantity=sku.quantity,
            in_stock=sku.in_stock,
            characteristics=[
                CharacteristicResponse.from_domain(characteristic)
                for characteristic in sku.characteristics
            ],
            images=[ImageResponse.from_domain(image) for image in sku.images],
        )


class ProductResponse(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str
    images: list[ImageResponse]
    status: ProductStatus
    characteristics: list[CharacteristicResponse]
    skus: list[SkuResponse]

    @classmethod
    def from_domain(cls, product: Product) -> ProductResponse:
        return cls(
            id=product.id,
            slug=product.slug,
            title=product.title,
            description=product.description,
            images=[ImageResponse.from_domain(image) for image in product.images],
            status=product.status,
            characteristics=[
                CharacteristicResponse.from_domain(characteristic)
                for characteristic in product.characteristics
            ],
            skus=[SkuResponse.from_domain(sku) for sku in product.skus],
        )
