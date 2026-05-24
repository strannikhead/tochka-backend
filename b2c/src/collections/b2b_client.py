from __future__ import annotations

import os
from typing import Any, Protocol
from uuid import UUID

import httpx
from src.collections.domain import B2BProductCard, B2BProductImage


class CollectionsB2BClient(Protocol):
    async def get_products_batch(self, product_ids: list[UUID]) -> dict[UUID, B2BProductCard]: ...


class CollectionsB2BError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class InMemoryCollectionsB2BClient:
    def __init__(self, products: dict[UUID, B2BProductCard] | None = None) -> None:
        self._products: dict[UUID, B2BProductCard] = products if products is not None else {}

    async def get_products_batch(self, product_ids: list[UUID]) -> dict[UUID, B2BProductCard]:
        return {pid: self._products[pid] for pid in product_ids if pid in self._products}


class HttpCollectionsB2BClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 5.0,
        service_key: str | None = None,
    ) -> None:
        self._base_url = (base_url or os.getenv("B2B_BASE_URL") or "http://localhost:8001").rstrip(
            "/"
        )
        self._timeout = timeout
        self._service_key = service_key or os.getenv("B2B_SERVICE_KEY")

    @property
    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._service_key:
            headers["X-Service-Key"] = self._service_key
        return headers

    async def get_products_batch(self, product_ids: list[UUID]) -> dict[UUID, B2BProductCard]:
        if not product_ids:
            return {}

        url = f"{self._base_url}/api/v1/public/products/batch"
        payload = {"product_ids": [str(pid) for pid in product_ids]}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=self._headers)
        except httpx.RequestError as exc:
            raise CollectionsB2BError("Unable to reach B2B", None) from exc

        if response.status_code in {502, 503}:
            raise CollectionsB2BError("B2B temporarily unavailable", response.status_code)
        if response.status_code != 200:
            raise CollectionsB2BError(
                f"Unexpected B2B response: {response.status_code}", response.status_code
            )

        body = response.json()
        if not isinstance(body, list):
            raise CollectionsB2BError("Unexpected B2B response shape", response.status_code)

        requested = {UUID(str(pid)) for pid in product_ids}
        result: dict[UUID, B2BProductCard] = {}
        for item in body:
            card = _parse_product_card(item)
            if card.id in requested:
                result[card.id] = card
        return result


def _parse_product_card(payload: dict[str, Any]) -> B2BProductCard:
    product_id = UUID(payload["id"])
    skus = payload.get("skus") or []
    prices = [int(sku["price"]) for sku in skus if "price" in sku]
    stocks = [int(sku.get("stock_quantity", 0) or 0) for sku in skus]
    min_price = min(prices) if prices else 0
    has_stock = any(stock > 0 for stock in stocks)

    raw_images = payload.get("images") or []
    images = tuple(
        B2BProductImage(
            id=UUID(image["id"]),
            url=str(image["url"]),
            ordering=int(image.get("ordering", 0) or 0),
            is_main=int(image.get("ordering", 0) or 0) == 0,
        )
        for image in raw_images
    )

    return B2BProductCard(
        id=product_id,
        name=str(payload.get("title", "")),
        slug=payload.get("slug"),
        min_price=min_price,
        has_stock=has_stock,
        images=images,
    )
