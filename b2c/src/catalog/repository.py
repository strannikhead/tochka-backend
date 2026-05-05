from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import httpx
from src.catalog.domain import Facet, Facets, FacetValue, ProductShort, ProductShortList


class CatalogRepository(Protocol):
    async def list_products(
        self,
        *,
        category_id: UUID | None,
        filters: dict[str, list[str]] | None,
        sort: str | None,
        limit: int,
        offset: int,
        search: str | None,
    ) -> ProductShortList: ...

    async def get_facets(
        self,
        *,
        category_id: UUID,
        filters: dict[str, list[str]] | None,
    ) -> Facets: ...


class UpstreamServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class CatalogProduct:
    id: UUID
    title: str
    image: str
    price: int
    in_stock: bool
    is_in_cart: bool
    category_id: UUID
    attributes: dict[str, str | int | float | bool]
    rating: float
    popularity: int
    created_at: datetime
    discount: int

    def to_short(self) -> ProductShort:
        return ProductShort(
            id=self.id,
            title=self.title,
            image=self.image,
            price=self.price,
            in_stock=self.in_stock,
            is_in_cart=self.is_in_cart,
        )


class InMemoryCatalogRepository:
    def __init__(
        self,
        products: list[CatalogProduct] | None = None,
        categories: set[UUID] | None = None,
    ) -> None:
        self._products = products if products is not None else _default_catalog_products()
        self._categories = (
            categories
            if categories is not None
            else {product.category_id for product in self._products}
        )

    async def list_products(
        self,
        *,
        category_id: UUID | None,
        filters: dict[str, list[str]] | None,
        sort: str | None,
        limit: int,
        offset: int,
        search: str | None,
    ) -> ProductShortList:
        if category_id is not None and category_id not in self._categories:
            raise UpstreamServiceError("Category not found", 404)

        filters = filters or {}
        filtered = [
            product
            for product in self._products
            if _matches_category(product, category_id)
            and _matches_filters(product, filters)
            and _matches_search(product, search)
        ]

        sorted_products = _sort_products(filtered, sort)
        total_count = len(sorted_products)
        paginated = sorted_products[offset : offset + limit]
        items = tuple(product.to_short() for product in paginated)
        return ProductShortList(items=items, total_count=total_count, limit=limit, offset=offset)

    async def get_facets(
        self,
        *,
        category_id: UUID,
        filters: dict[str, list[str]] | None,
    ) -> Facets:
        if category_id not in self._categories:
            raise UpstreamServiceError("Category not found", 404)

        filters = filters or {}
        filtered = [
            product
            for product in self._products
            if _matches_category(product, category_id) and _matches_filters(product, filters)
        ]

        facet_counts: dict[str, dict[str, int]] = {}
        for product in filtered:
            for key, value in product.attributes.items():
                normalized = str(value)
                facet_counts.setdefault(key, {})
                facet_counts[key][normalized] = facet_counts[key].get(normalized, 0) + 1

        facets = []
        for name in sorted(facet_counts):
            values = [
                FacetValue(value=value, count=count)
                for value, count in sorted(facet_counts[name].items())
            ]
            facets.append(Facet(name=name, values=tuple(values)))

        return Facets(category_id=category_id, facets=tuple(facets))


class HttpCatalogRepository:
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

    async def list_products(
        self,
        *,
        category_id: UUID | None,
        filters: dict[str, list[str]] | None,
        sort: str | None,
        limit: int,
        offset: int,
        search: str | None,
    ) -> ProductShortList:
        params = _build_product_params(
            category_id=category_id,
            filters=filters or {},
            sort=sort,
            limit=limit,
            offset=offset,
            search=search,
        )
        payload = await self._get("/api/v1/products", params)
        return _parse_product_short_list(payload)

    async def get_facets(
        self,
        *,
        category_id: UUID,
        filters: dict[str, list[str]] | None,
    ) -> Facets:
        params = _build_facets_params(category_id=category_id, filters=filters or {})
        payload = await self._get("/api/v1/catalog/facets", params)
        return _parse_facets(payload)

    async def _get(self, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {}
        if self._service_key:
            headers["X-Service-Key"] = self._service_key
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.RequestError as exc:
            raise UpstreamServiceError("Unable to reach B2B", None) from exc

        if response.status_code in {502, 503}:
            raise UpstreamServiceError("B2B temporarily unavailable", response.status_code)
        if response.status_code == 404:
            raise UpstreamServiceError("Category not found", response.status_code)
        if response.status_code == 400:
            raise UpstreamServiceError("Invalid upstream request", response.status_code)
        if response.status_code != 200:
            raise UpstreamServiceError("Unexpected upstream response", response.status_code)

        return response.json()


def _matches_category(product: CatalogProduct, category_id: UUID | None) -> bool:
    return category_id is None or product.category_id == category_id


def _matches_filters(product: CatalogProduct, filters: dict[str, list[str]]) -> bool:
    for key, values in filters.items():
        if not values:
            continue
        if key not in product.attributes:
            return False
        product_value = _normalize_value(product.attributes[key])
        normalized_values = {_normalize_value(value) for value in values}
        if product_value not in normalized_values:
            return False
    return True


def _matches_search(product: CatalogProduct, search: str | None) -> bool:
    if not search:
        return True
    return search.lower() in product.title.lower()


def _sort_products(products: list[CatalogProduct], sort: str | None) -> list[CatalogProduct]:
    sort_value = sort or "rating"
    key_map: dict[str, tuple[Callable[[CatalogProduct], Any], bool]] = {
        "rating": (lambda product: product.rating, True),
        "popularity": (lambda product: product.popularity, True),
        "price_asc": (lambda product: product.price, False),
        "price_desc": (lambda product: product.price, True),
        "date_desc": (lambda product: product.created_at, True),
        "discount_desc": (lambda product: product.discount, True),
    }
    key_func, reverse = key_map.get(sort_value, key_map["rating"])
    return sorted(products, key=key_func, reverse=reverse)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            if "." in lowered:
                return float(lowered)
            return int(lowered)
        except ValueError:
            return value
    return value


def _build_product_params(
    *,
    category_id: UUID | None,
    filters: dict[str, list[str]],
    sort: str | None,
    limit: int,
    offset: int,
    search: str | None,
) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = [("limit", str(limit)), ("offset", str(offset))]
    if category_id is not None:
        params.append(("category_id", str(category_id)))
    if sort:
        params.append(("sort", sort))
    if search:
        params.append(("search", search))
    for key, values in filters.items():
        for value in values:
            params.append((f"filters[{key}]", str(value)))
    return params


def _build_facets_params(
    *,
    category_id: UUID,
    filters: dict[str, list[str]],
) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = [("category_id", str(category_id))]
    for key, values in filters.items():
        for value in values:
            params.append((f"filters[{key}]", str(value)))
    return params


def _parse_product_short_list(payload: dict[str, Any]) -> ProductShortList:
    items = tuple(_parse_product_short(item) for item in payload.get("items", []) or [])
    return ProductShortList(
        items=items,
        total_count=int(payload.get("total_count", len(items))),
        limit=int(payload.get("limit", len(items))),
        offset=int(payload.get("offset", 0)),
    )


def _parse_product_short(payload: dict[str, Any]) -> ProductShort:
    return ProductShort(
        id=UUID(payload["id"]),
        title=str(payload.get("title", "")),
        image=str(payload.get("image", "")),
        price=int(payload.get("price", 0)),
        in_stock=bool(payload.get("in_stock", False)),
        is_in_cart=bool(payload.get("is_in_cart", False)),
    )


def _parse_facets(payload: dict[str, Any]) -> Facets:
    category_id = UUID(payload["category_id"])
    facets_payload = payload.get("facets", []) or []
    facets = tuple(
        Facet(
            name=str(facet.get("name", "")),
            values=tuple(
                FacetValue(value=str(value.get("value", "")), count=int(value.get("count", 0)))
                for value in facet.get("values", []) or []
            ),
        )
        for facet in facets_payload
    )
    return Facets(category_id=category_id, facets=facets)


def _default_catalog_products() -> list[CatalogProduct]:
    category_phones = UUID("123e4567-e89b-12d3-a456-426614174001")
    category_tv = UUID("123e4567-e89b-12d3-a456-426614174002")

    return [
        CatalogProduct(
            id=UUID("770e8400-e29b-41d4-a716-446655440002"),
            title="iPhone 15 Pro Max",
            image="https://example.com/images/iphone15.jpg",
            price=12999000,
            in_stock=True,
            is_in_cart=False,
            category_id=category_phones,
            attributes={"brand": "Apple", "color": "Black", "memory": 256},
            rating=4.9,
            popularity=120,
            created_at=datetime(2024, 2, 10, tzinfo=UTC),
            discount=0,
        ),
        CatalogProduct(
            id=UUID("770e8400-e29b-41d4-a716-446655440003"),
            title="Samsung Galaxy S24",
            image="https://example.com/images/s24.jpg",
            price=8999000,
            in_stock=True,
            is_in_cart=True,
            category_id=category_phones,
            attributes={"brand": "Samsung", "color": "White", "memory": 128},
            rating=4.7,
            popularity=200,
            created_at=datetime(2024, 1, 5, tzinfo=UTC),
            discount=500000,
        ),
        CatalogProduct(
            id=UUID("770e8400-e29b-41d4-a716-446655440004"),
            title="Xiaomi Redmi Note",
            image="https://example.com/images/redmi.jpg",
            price=3999000,
            in_stock=True,
            is_in_cart=False,
            category_id=category_phones,
            attributes={"brand": "Xiaomi", "color": "Black", "memory": 64},
            rating=4.3,
            popularity=300,
            created_at=datetime(2024, 2, 20, tzinfo=UTC),
            discount=250000,
        ),
        CatalogProduct(
            id=UUID("770e8400-e29b-41d4-a716-446655440010"),
            title="NeoVision 55",
            image="https://example.com/images/tv.jpg",
            price=5499000,
            in_stock=True,
            is_in_cart=False,
            category_id=category_tv,
            attributes={"brand": "NeoVision", "color": "Black"},
            rating=4.1,
            popularity=80,
            created_at=datetime(2024, 1, 20, tzinfo=UTC),
            discount=0,
        ),
    ]
