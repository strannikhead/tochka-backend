from __future__ import annotations

import os
import uuid
from typing import Any, Protocol
from uuid import UUID

import httpx

from product_card.domain import Characteristic, Image, Product, ProductStatus, Sku


class ProductRepository(Protocol):
    async def get_product(self, product_id: UUID) -> Product | None: ...


class UpstreamServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class InMemoryProductRepository:
    def __init__(self, products: dict[UUID, Product] | None = None) -> None:
        self._products = products if products is not None else _default_products()

    async def get_product(self, product_id: UUID) -> Product | None:
        return self._products.get(product_id)


class HttpProductRepository:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = (base_url or os.getenv("B2B_BASE_URL") or "http://localhost:8001").rstrip(
            "/"
        )
        self._timeout = timeout

    async def get_product(self, product_id: UUID) -> Product | None:
        url = f"{self._base_url}/api/v1/products/{product_id}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
        except httpx.RequestError as exc:
            raise UpstreamServiceError("Не удалось подключиться к B2B", None) from exc

        if response.status_code == 404:
            return None
        if response.status_code in {502, 503}:
            raise UpstreamServiceError("B2B временно недоступен", response.status_code)
        if response.status_code != 200:
            raise UpstreamServiceError("Некорректный ответ от B2B", response.status_code)

        payload = response.json()
        return _parse_product(payload)


def _default_products() -> dict[UUID, Product]:
    product_id = uuid.UUID("770e8400-e29b-41d4-a716-446655440002")
    blocked_id = uuid.UUID("770e8400-e29b-41d4-a716-446655440099")

    product_images = (
        Image(
            url="https://images.steamusercontent.com/ugc/1248008971461813591/136B1A9E56BD56F0453117B4561B1B942AC93024/?imw=512&amp;&amp;ima=fit&amp;impolicy=Letterbox&amp;imcolor=%23000000&amp;letterbox=false",
            order=1,
        ),
        Image(
            url="https://i.pinimg.com/736x/a6/f9/e9/a6f9e975d2cae3463d66d7a40a6cfe23.jpg", order=2
        ),
    )
    product_characteristics = (
        Characteristic(name="BRAND", value="Apple"),
        Characteristic(name="COLOR", value="Silver"),
    )

    product_skus = (
        Sku(
            id=uuid.UUID("660e8400-e29b-41d4-a716-446655440001"),
            name="iPhone 14 Pro 128GB Silver",
            price=99999,
            discount=0,
            quantity=15,
            characteristics=(
                Characteristic(name="COLOR", value="Silver"),
                Characteristic(name="MEMORY", value="128GB"),
            ),
            images=(
                Image(
                    url="https://images.steamusercontent.com/ugc/1248008971461813591/136B1A9E56BD56F0453117B4561B1B942AC93024/?imw=512&amp;&amp;ima=fit&amp;impolicy=Letterbox&amp;imcolor=%23000000&amp;letterbox=false",
                    order=1,
                ),
            ),
        ),
        Sku(
            id=uuid.UUID("660e8400-e29b-41d4-a716-446655440002"),
            name="iPhone 14 Pro 256GB Gold",
            price=109999,
            discount=5000,
            quantity=0,
            characteristics=(
                Characteristic(name="COLOR", value="Gold"),
                Characteristic(name="MEMORY", value="256GB"),
            ),
            images=(
                Image(
                    url="https://i.pinimg.com/736x/a6/f9/e9/a6f9e975d2cae3463d66d7a40a6cfe23.jpg",
                    order=1,
                ),
            ),
        ),
    )

    product = Product(
        id=product_id,
        slug="iphone-14-pro",
        title="iPhone 14 Pro",
        description="Смартфон Apple iPhone 14 Pro с диагональю 6.1 дюйма",
        images=product_images,
        status=ProductStatus.MODERATED,
        characteristics=product_characteristics,
        skus=product_skus,
    )

    blocked_product = Product(
        id=blocked_id,
        slug="iphone-14-pro-blocked",
        title="iPhone 14 Pro",
        description="Смартфон Apple iPhone 14 Pro с диагональю 6.1 дюйма",
        images=product_images,
        status=ProductStatus.BLOCKED,
        characteristics=product_characteristics,
        skus=product_skus,
    )

    return {product_id: product, blocked_id: blocked_product}


def _parse_product(payload: dict[str, Any]) -> Product:
    status_raw = str(payload.get("status", ProductStatus.CREATED))
    try:
        status = ProductStatus(status_raw)
    except ValueError:
        status = ProductStatus.CREATED

    return Product(
        id=UUID(payload["id"]),
        slug=str(payload.get("slug", "")),
        title=str(payload.get("title", "")),
        description=str(payload.get("description", "")),
        images=tuple(_parse_image(image) for image in payload.get("images", []) or []),
        status=status,
        characteristics=tuple(
            _parse_characteristic(characteristic)
            for characteristic in payload.get("characteristics", []) or []
        ),
        skus=tuple(_parse_sku(sku) for sku in payload.get("skus", []) or []),
    )


def _parse_image(payload: dict[str, Any]) -> Image:
    order = payload.get("order")
    if order is None:
        order = payload.get("ordering", 0)
    return Image(url=str(payload.get("url", "")), order=int(order))


def _parse_characteristic(payload: dict[str, Any]) -> Characteristic:
    return Characteristic(name=str(payload.get("name", "")), value=str(payload.get("value", "")))


def _parse_sku(payload: dict[str, Any]) -> Sku:
    quantity = payload.get("quantity")
    if quantity is None:
        quantity = payload.get("active_quantity", 0)
    discount = payload.get("discount", 0)
    images_payload = payload.get("images")
    if images_payload is None:
        image_url = payload.get("image")
        images = (Image(url=str(image_url), order=0),) if image_url else ()
    else:
        images = tuple(_parse_image(image) for image in images_payload or [])

    return Sku(
        id=UUID(payload["id"]),
        name=str(payload.get("name", "")),
        price=int(payload.get("price", 0)),
        discount=int(discount),
        quantity=int(quantity),
        characteristics=tuple(
            _parse_characteristic(characteristic)
            for characteristic in payload.get("characteristics", []) or []
        ),
        images=images,
    )
