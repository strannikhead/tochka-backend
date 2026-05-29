from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import httpx


class CategoryRepository(Protocol):
    async def list_categories(self) -> list[CategoryRecord]: ...

    async def get_category(self, category_id: UUID) -> CategoryRecord: ...

    async def count_products(self, category_id: UUID) -> int: ...

    async def get_product_category_id(self, product_id: UUID) -> UUID: ...


class UpstreamServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class CategoryRecord:
    id: UUID
    name: str
    parent_id: UUID | None
    level: int = 0
    path: tuple[str, ...] = ()
    slug: str | None = None
    description: str | None = None
    image_url: str | None = None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class InMemoryCategoryRepository:
    def __init__(
        self,
        *,
        categories: Sequence[CategoryRecord],
        product_categories: dict[UUID, UUID] | None = None,
        product_counts: dict[UUID, int] | None = None,
    ) -> None:
        self._categories = list(categories)
        self._categories_by_id = {category.id: category for category in self._categories}
        self._product_categories = dict(product_categories or {})
        self._product_counts = dict(product_counts or {})

    async def list_categories(self) -> list[CategoryRecord]:
        return list(self._categories)

    async def get_category(self, category_id: UUID) -> CategoryRecord:
        category = self._categories_by_id.get(category_id)
        if category is None:
            raise UpstreamServiceError("Category not found", 404)
        return category

    async def count_products(self, category_id: UUID) -> int:
        if category_id not in self._categories_by_id:
            raise UpstreamServiceError("Category not found", 404)
        if category_id in self._product_counts:
            return self._product_counts[category_id]
        return sum(1 for value in self._product_categories.values() if value == category_id)

    async def get_product_category_id(self, product_id: UUID) -> UUID:
        category_id = self._product_categories.get(product_id)
        if category_id is None:
            raise UpstreamServiceError("Product not found", 404)
        return category_id


class HttpCategoryRepository:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 5.0,
        service_key: str | None = None,
    ) -> None:
        import os

        self._base_url = (base_url or os.getenv("B2B_BASE_URL") or "http://localhost:8001").rstrip(
            "/"
        )
        self._timeout = timeout
        self._service_key = service_key or os.getenv("B2B_SERVICE_KEY")

    async def list_categories(self) -> list[CategoryRecord]:
        payload = await self._request_json("GET", "/api/v1/categories")
        return [_parse_category(item) for item in _extract_items(payload)]

    async def get_category(self, category_id: UUID) -> CategoryRecord:
        payload = await self._request_json("GET", f"/api/v1/categories/{category_id}")
        if not isinstance(payload, dict):
            raise UpstreamServiceError("Unexpected upstream response", 502)
        return _parse_category(payload, category_id=category_id)

    async def count_products(self, category_id: UUID) -> int:
        payload = await self._request_json(
            "GET",
            "/api/v1/products",
            params={"category_id": str(category_id), "limit": 1, "offset": 0},
        )
        if not isinstance(payload, dict):
            raise UpstreamServiceError("Unexpected upstream response", 502)
        total_count = payload.get("total_count")
        if isinstance(total_count, int):
            return total_count
        raise UpstreamServiceError("Unexpected upstream response", 502)

    async def get_product_category_id(self, product_id: UUID) -> UUID:
        payload = await self._request_json("GET", f"/api/v1/products/{product_id}")
        if not isinstance(payload, dict):
            raise UpstreamServiceError("Unexpected upstream response", 502)
        category = payload.get("category")
        if isinstance(category, dict) and category.get("id"):
            return UUID(str(category["id"]))
        if payload.get("category_id"):
            return UUID(str(payload["category_id"]))
        raise UpstreamServiceError("Unexpected upstream response", 502)

    async def _request_json(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        headers: dict[str, str] = {}
        if self._service_key:
            headers["X-Service-Key"] = self._service_key

        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(method, url, params=params, headers=headers)
        except httpx.RequestError as exc:
            raise UpstreamServiceError("Unable to reach B2B", None) from exc

        if response.status_code in {502, 503}:
            raise UpstreamServiceError("B2B temporarily unavailable", response.status_code)
        if response.status_code == 404:
            message = (
                "Category not found"
                if path.startswith("/api/v1/categories")
                else "Product not found"
            )
            raise UpstreamServiceError(message, 404)
        if response.status_code == 400:
            raise UpstreamServiceError("Invalid upstream request", response.status_code)
        if response.status_code != 200:
            raise UpstreamServiceError("Unexpected upstream response", response.status_code)
        return response.json()


def get_category_repository() -> CategoryRepository:
    return HttpCategoryRepository()


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    raise UpstreamServiceError("Unexpected upstream response", 502)


def _parse_category(payload: dict[str, Any], category_id: UUID | None = None) -> CategoryRecord:
    raw_id = payload.get("id") or category_id
    if raw_id is None:
        raise UpstreamServiceError("Unexpected upstream response", 502)
    parsed_id = UUID(str(raw_id))
    raw_parent_id = payload.get("parent_id")
    parent_id = UUID(str(raw_parent_id)) if raw_parent_id else None
    path = payload.get("path") if isinstance(payload.get("path"), list) else []
    slug = payload.get("slug")
    return CategoryRecord(
        id=parsed_id,
        name=str(payload.get("name", "")),
        parent_id=parent_id,
        level=int(payload.get("level", len(path) - 1 if path else 0)),
        path=tuple(str(item) for item in path),
        slug=str(slug) if slug is not None else None,
        description=payload.get("description"),
        image_url=payload.get("image_url"),
        is_active=bool(payload.get("is_active", True)),
        created_at=_parse_datetime(payload.get("created_at")),
        updated_at=_parse_datetime(payload.get("updated_at")),
    )


def _parse_datetime(value: Any) -> datetime:
    if value is None:
        return datetime.now(UTC)
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)
