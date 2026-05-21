from __future__ import annotations

import os
import uuid
from typing import Any, Protocol
from uuid import UUID

import httpx

from b2c.src.product_card.domain import Characteristic, Image, Product, ProductStatus, Sku


class ProductRepository(Protocol):
    async def get_product(self, product_id: UUID) -> Product | None: ...

    async def get_similar_products(self, product_id: UUID, limit: int) -> list[Product]: ...


class UpstreamServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class InMemoryProductRepository:
    def __init__(self, products: dict[UUID, Product] | None = None) -> None:
        self._products = products if products is not None else _default_products()

    async def get_product(self, product_id: UUID) -> Product | None:
        return self._products.get(product_id)

    async def get_similar_products(self, product_id: UUID, limit: int) -> list[Product]:
        return [
            product
            for product_id_value, product in self._products.items()
            if product_id_value != product_id
        ][:limit]


class HttpProductRepository:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = (base_url or os.getenv("B2B_BASE_URL") or "http://localhost:8001").rstrip(
            "/"
        )
        self._service_key = os.getenv("B2B_SERVICE_KEY", "dev-service-key")
        self._timeout = timeout

    async def get_product(self, product_id: UUID) -> Product | None:
        url = f"{self._base_url}/api/v1/public/products/{product_id}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers={"X-Service-Key": self._service_key})
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

    async def get_similar_products(self, product_id: UUID, limit: int) -> list[Product]:
        url = f"{self._base_url}/api/v1/public/products/{product_id}/similar"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    url,
                    headers={"X-Service-Key": self._service_key},
                    params={"limit": limit},
                )
        except httpx.RequestError as exc:
            raise UpstreamServiceError("Не удалось подключиться к B2B", None) from exc

        if response.status_code in {502, 503}:
            raise UpstreamServiceError("B2B временно недоступен", response.status_code)
        if response.status_code != 200:
            raise UpstreamServiceError("Некорректный ответ от B2B", response.status_code)

        payload = response.json()
        return [_parse_product(product) for product in payload]


def _default_products() -> dict[UUID, Product]:
    product_id = uuid.UUID("770e8400-e29b-41d4-a716-446655440002")
    blocked_id = uuid.UUID("770e8400-e29b-41d4-a716-446655440099")

    product_image_id = uuid.UUID("111e8400-e29b-41d4-a716-446655440000")
    sku_image_id = uuid.UUID("222e8400-e29b-41d4-a716-446655440000")

    product_images = (
        Image(
            id=product_image_id,
            url="https://images.steamusercontent.com/ugc/1248008971461813591/136B1A9E56BD56F0453117B4561B1B942AC93024/?imw=512&amp;&amp;ima=fit&amp;impolicy=Letterbox&amp;imcolor=%23000000&amp;letterbox=false",
            ordering=1,
        ),
        Image(
            id=uuid.UUID("111e8400-e29b-41d4-a716-446655440001"),
            url="https://i.pinimg.com/736x/a6/f9/e9/a6f9e975d2cae3463d66d7a40a6cfe23.jpg",
            ordering=2,
        ),
    )
    product_characteristics = (
        Characteristic(name="BRAND", value="Apple"),
        Characteristic(name="COLOR", value="Silver"),
    )

    product_skus = (
        Sku(
            id=uuid.UUID("660e8400-e29b-41d4-a716-446655440001"),
            product_id=product_id,
            name="iPhone 14 Pro 128GB Silver",
            sku_code="IP14P-128-S",
            price=99999,
            discount=0,
            stock_quantity=15,
            active_quantity=15,
            characteristics=(
                Characteristic(name="COLOR", value="Silver"),
                Characteristic(name="MEMORY", value="128GB"),
            ),
            images=(
                Image(
                    id=sku_image_id,
                    url="https://images.steamusercontent.com/ugc/1248008971461813591/136B1A9E56BD56F0453117B4561B1B942AC93024/?imw=512&amp;&amp;ima=fit&amp;impolicy=Letterbox&amp;imcolor=%23000000&amp;letterbox=false",
                    ordering=1,
                ),
            ),
        ),
        Sku(
            id=uuid.UUID("660e8400-e29b-41d4-a716-446655440002"),
            product_id=product_id,
            name="iPhone 14 Pro 256GB Gold",
            sku_code="IP14P-256-G",
            price=109999,
            discount=5000,
            stock_quantity=0,
            active_quantity=0,
            characteristics=(
                Characteristic(name="COLOR", value="Gold"),
                Characteristic(name="MEMORY", value="256GB"),
            ),
            images=(
                Image(
                    id=uuid.UUID("222e8400-e29b-41d4-a716-446655440001"),
                    url="https://i.pinimg.com/736x/a6/f9/e9/a6f9e975d2cae3463d66d7a40a6cfe23.jpg",
                    ordering=1,
                ),
            ),
        ),
    )

    product = Product(
        id=product_id,
        slug="iphone-14-pro",
        name="iPhone 14 Pro",
        description="Смартфон Apple iPhone 14 Pro с диагональю 6.1 дюйма",
        images=product_images,
        status=ProductStatus.MODERATED,
        characteristics=product_characteristics,
        skus=product_skus,
        min_price=99999,
    )

    blocked_product = Product(
        id=blocked_id,
        slug="iphone-14-pro-blocked",
        name="iPhone 14 Pro",
        description="Смартфон Apple iPhone 14 Pro с диагональю 6.1 дюйма",
        images=product_images,
        status=ProductStatus.BLOCKED,
        characteristics=product_characteristics,
        skus=product_skus,
        min_price=99999,
    )

    return {product_id: product, blocked_id: blocked_product}


def _parse_product(payload: dict[str, Any]) -> Product:
    status_raw = str(payload.get("status", ProductStatus.CREATED))
    try:
        status = ProductStatus(status_raw)
    except ValueError:
        status = ProductStatus.CREATED

    images_payload = payload.get("images", []) or []
    images = tuple(_parse_image(image) for image in images_payload)
    if not images and payload.get("cover_image"):
        images = (
            Image(
                id=uuid.uuid4(),
                url=str(payload.get("cover_image")),
                ordering=0,
            ),
        )

    return Product(
        id=UUID(payload["id"]),
        name=str(payload.get("title", payload.get("name", ""))),
        slug=str(payload.get("slug", "")),
        description=str(payload.get("description", "")),
        images=images,
        status=status,
        characteristics=tuple(
            _parse_characteristic(characteristic)
            for characteristic in payload.get("characteristics", []) or []
        ),
        skus=tuple(_parse_sku(sku) for sku in payload.get("skus", []) or []),
        min_price=payload.get("min_price"),
    )


def _parse_image(payload: dict[str, Any]) -> Image:
    ordering = payload.get("ordering")
    if ordering is None:
        ordering = payload.get("order", 0)
    return Image(
        id=UUID(payload.get("id")) if payload.get("id") else uuid.uuid4(),
        url=str(payload.get("url", "")),
        ordering=int(ordering),
        alt=payload.get("alt"),
        is_main=payload.get("is_main"),
    )


def _parse_characteristic(payload: dict[str, Any]) -> Characteristic:
    raw_id = payload.get("id")
    return Characteristic(
        name=str(payload.get("name", "")),
        value=str(payload.get("value", "")),
        id=UUID(raw_id) if raw_id else None,
    )


def _parse_sku(payload: dict[str, Any]) -> Sku:
    stock_quantity = payload.get("stock_quantity", 0)
    active_quantity = payload.get("active_quantity", 0)
    discount = payload.get("discount", 0)
    images_payload = payload.get("images")
    if images_payload is None:
        image_url = payload.get("image")
        images = (Image(id=uuid.uuid4(), url=str(image_url), ordering=0),) if image_url else ()
    else:
        images = tuple(_parse_image(image) for image in images_payload or [])

    return Sku(
        id=UUID(payload["id"]),
        product_id=UUID(payload["product_id"]) if payload.get("product_id") else None,
        name=str(payload.get("name", "")),
        sku_code=payload.get("article"),
        price=int(payload.get("price", 0)),
        discount=int(discount),
        stock_quantity=int(stock_quantity),
        active_quantity=int(active_quantity),
        characteristics=tuple(
            _parse_characteristic(characteristic)
            for characteristic in payload.get("characteristics", []) or []
        ),
        images=images,
    )
