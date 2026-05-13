from __future__ import annotations

import os
from typing import Any, Protocol
from uuid import UUID

import httpx

from src.cart.domain import B2BSkuData


class B2BCartClient(Protocol):
    async def get_sku_data(self, sku_id: UUID) -> B2BSkuData | None: ...

    async def check_sku_for_add(
        self, sku_id: UUID, quantity: int
    ) -> tuple[B2BSkuData | None, str | None]: ...


class B2BCartError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class InMemoryB2BCartClient:
    def __init__(self, skus: dict[UUID, B2BSkuData] | None = None) -> None:
        self._skus: dict[UUID, B2BSkuData] = skus if skus is not None else {}

    async def get_sku_data(self, sku_id: UUID) -> B2BSkuData | None:
        return self._skus.get(sku_id)

    async def check_sku_for_add(
        self, sku_id: UUID, quantity: int
    ) -> tuple[B2BSkuData | None, str | None]:
        sku = self._skus.get(sku_id)
        if sku is None:
            return None, "SKU_NOT_FOUND"
        if sku.product_status == "BLOCKED":
            return sku, "SKU_NOT_AVAILABLE"
        if sku.product_status not in ("MODERATED",):
            return sku, "SKU_NOT_AVAILABLE"
        if sku.stock_quantity == 0:
            return sku, "SKU_NOT_AVAILABLE"
        if sku.stock_quantity < quantity:
            return sku, "INSUFFICIENT_STOCK"
        return sku, None


class HttpB2BCartClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 5.0,
        service_key: str | None = None,
    ) -> None:
        self._base_url = (
            base_url or os.getenv("B2B_BASE_URL") or "http://localhost:8001"
        ).rstrip("/")
        self._timeout = timeout
        self._service_key = service_key or os.getenv("B2B_SERVICE_KEY")

    @property
    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._service_key:
            headers["X-Service-Key"] = self._service_key
        return headers

    async def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=self._headers)
        except httpx.RequestError as exc:
            raise B2BCartError("Unable to reach B2B", None) from exc
        if response.status_code in {502, 503}:
            raise B2BCartError("B2B temporarily unavailable", response.status_code)
        if response.status_code == 404:
            raise B2BCartError("Not found", 404)
        if response.status_code != 200:
            raise B2BCartError(
                f"Unexpected B2B response: {response.status_code}", response.status_code
            )
        return response.json()

    async def get_sku_data(self, sku_id: UUID) -> B2BSkuData | None:
        try:
            sku_payload = await self._get(f"/api/public/skus/{sku_id}")
        except B2BCartError as exc:
            if exc.status_code == 404:
                return None
            raise
        product_id = UUID(sku_payload["product_id"])
        try:
            product_payload = await self._get(f"/api/public/products/{product_id}")
        except B2BCartError as exc:
            if exc.status_code == 404:
                return None
            raise
        images = sku_payload.get("images") or []
        image_url = images[0]["url"] if images else None
        return B2BSkuData(
            sku_id=sku_id,
            product_id=product_id,
            sku_name=sku_payload["name"],
            price=int(sku_payload["price"]),
            stock_quantity=int(sku_payload["stock_quantity"]),
            image_url=image_url,
            product_title=product_payload["title"],
            product_status=product_payload["status"],
        )

    async def check_sku_for_add(
        self, sku_id: UUID, quantity: int
    ) -> tuple[B2BSkuData | None, str | None]:
        sku = await self.get_sku_data(sku_id)
        if sku is None:
            return None, "SKU_NOT_FOUND"
        if sku.product_status == "BLOCKED":
            return sku, "SKU_NOT_AVAILABLE"
        if sku.product_status not in ("MODERATED",):
            return sku, "SKU_NOT_AVAILABLE"
        if sku.stock_quantity == 0:
            return sku, "SKU_NOT_AVAILABLE"
        if sku.stock_quantity < quantity:
            return sku, "INSUFFICIENT_STOCK"
        return sku, None
