from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from b2c.src.api.errors import error_response


class CategoryNotFoundError(Exception):
    pass


class OrphanNodeError(Exception):
    pass


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


class CategoryRepository(Protocol):
    async def list_categories(self) -> list[CategoryRecord]: ...

    async def get_category(self, category_id: UUID) -> CategoryRecord: ...

    async def count_products(self, category_id: UUID) -> int: ...

    async def get_product_category_id(self, product_id: UUID) -> UUID: ...


class UpstreamServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CategoryRefResponse(BaseModel):
    id: UUID
    name: str
    parent_id: UUID | None
    level: int
    path: list[str]


class CategoryTreeNodeResponse(CategoryRefResponse):
    children: list[CategoryTreeNodeResponse] = Field(default_factory=list)


CategoryTreeNodeResponse.model_rebuild()


class CategoriesTreeEnvelope(BaseModel):
    items: list[CategoryTreeNodeResponse]


class CategoryParentResponse(BaseModel):
    id: UUID
    name: str
    slug: str


class CategorySeoResponse(BaseModel):
    title: str
    description: str
    keywords: list[str]


class CategoryMetaTagsResponse(BaseModel):
    og_title: str
    og_description: str


class CategoryDetailResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str | None = None
    parent: CategoryParentResponse | None = None
    product_count: int | None = None
    seo: CategorySeoResponse
    meta_tags: CategoryMetaTagsResponse
    image_url: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None


class BreadcrumbItemResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    url: str
    level: int
    is_current: bool


class BreadcrumbMetaResponse(BaseModel):
    resolved_via: str
    category_id: UUID | None = None
    product_id: UUID | None = None


class BreadcrumbsResponse(BaseModel):
    data: list[BreadcrumbItemResponse]
    meta: BreadcrumbMetaResponse


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

    path = payload.get("path") if isinstance(payload.get("path"), list) else []
    raw_parent_id = payload.get("parent_id")
    return CategoryRecord(
        id=UUID(str(raw_id)),
        name=str(payload.get("name", "")),
        parent_id=UUID(str(raw_parent_id)) if raw_parent_id else None,
        level=int(payload.get("level", len(path) - 1 if path else 0)),
        path=tuple(str(item) for item in path),
        slug=str(payload.get("slug")) if payload.get("slug") is not None else None,
        description=payload.get("description"),
        image_url=payload.get("image_url"),
        is_active=bool(payload.get("is_active", True)),
        created_at=_parse_datetime(payload.get("created_at")),
        updated_at=_parse_datetime(payload.get("updated_at")),
    )


router = APIRouter(prefix="/api/v1/catalog/categories", tags=["Catalog"])
legacy_router = APIRouter(prefix="/api/v1", tags=["Catalog"], include_in_schema=False)


@router.get("", response_model=list[CategoryRefResponse])
async def list_categories(
    response: Response,
    repository: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> list[CategoryRefResponse] | JSONResponse:
    categories, error = await _load_categories(repository)
    if error is not None:
        return error
    response.headers["Cache-Control"] = "max-age=3600"
    return build_category_refs(categories)


@router.get("/tree", response_model=list[CategoryTreeNodeResponse])
async def get_categories_tree(
    response: Response,
    repository: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> list[CategoryTreeNodeResponse] | JSONResponse:
    categories, error = await _load_categories(repository)
    if error is not None:
        return error
    try:
        tree = build_category_tree(categories)
    except OrphanNodeError:
        return _navigation_error(422, "orphan_node", "category hierarchy is broken")
    response.headers["Cache-Control"] = "max-age=3600"
    return tree


@router.get("/{id}/filters", include_in_schema=False)
async def get_category_filters(
    id: str,
    repository: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> JSONResponse:
    try:
        category_uuid = UUID(id)
    except ValueError:
        return error_response(400, "INVALID_REQUEST", "Invalid category_id")

    try:
        await repository.get_category(category_uuid)
        payload = await _fetch_category_filters(category_uuid)
    except UpstreamServiceError as exc:
        return _upstream_error(exc)

    return JSONResponse(content=payload)


@legacy_router.get("/categories", response_model=CategoriesTreeEnvelope)
async def get_categories_tree_alias(
    response: Response,
    repository: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> CategoriesTreeEnvelope | JSONResponse:
    categories, error = await _load_categories(repository)
    if error is not None:
        return error
    try:
        tree = build_category_tree(categories)
    except OrphanNodeError:
        return _navigation_error(422, "orphan_node", "category hierarchy is broken")
    response.headers["Cache-Control"] = "max-age=3600"
    return CategoriesTreeEnvelope(items=tree)


@legacy_router.get(
    "/categories/{id}", response_model=CategoryDetailResponse, include_in_schema=False
)
async def get_category(
    id: str,
    repository: Annotated[CategoryRepository, Depends(get_category_repository)],
    include_product_count: bool = Query(default=False),
) -> CategoryDetailResponse | JSONResponse:
    try:
        category_uuid = UUID(id)
    except ValueError:
        return error_response(400, "INVALID_REQUEST", "Invalid category_id")

    try:
        category = await repository.get_category(category_uuid)
        categories = await repository.list_categories()
        lineage = resolve_lineage(categories, category_uuid)
    except UpstreamServiceError as exc:
        if exc.status_code == 404:
            return error_response(404, "NOT_FOUND", "Category not found")
        return _upstream_error(exc)
    except CategoryNotFoundError:
        return error_response(404, "NOT_FOUND", "Category not found")
    except OrphanNodeError:
        return _navigation_error(422, "orphan_node", "category hierarchy is broken")

    parent = None
    if len(lineage) > 1:
        parent_category = lineage[-2]
        parent = CategoryParentResponse(
            id=parent_category.id,
            name=parent_category.name,
            slug=_category_slug(parent_category),
        )

    product_count = None
    if include_product_count:
        try:
            product_count = await repository.count_products(category_uuid)
        except UpstreamServiceError as exc:
            return _upstream_error(exc)

    name = category.name
    slug = _category_slug(category)

    return CategoryDetailResponse(
        id=category_uuid,
        name=name,
        slug=slug,
        description=category.description,
        parent=parent,
        product_count=product_count,
        seo=CategorySeoResponse(
            title=f"Купить {name.lower()} в интернет-магазине | NeoMarket",
            description=f"{name} по выгодным ценам. Бесплатная доставка.",
            keywords=[name.lower(), f"купить {name.lower()}", name],
        ),
        meta_tags=CategoryMetaTagsResponse(
            og_title=f"{name} | NeoMarket",
            og_description=f"Купить {name.lower()} в интернет-магазине.",
        ),
        image_url=category.image_url,
        is_active=category.is_active,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


@legacy_router.get("/breadcrumbs", response_model=BreadcrumbsResponse, include_in_schema=False)
async def get_breadcrumbs(
    repository: Annotated[CategoryRepository, Depends(get_category_repository)],
    category_id: str | None = Query(default=None),
    product_id: str | None = Query(default=None),
) -> BreadcrumbsResponse | JSONResponse:
    if category_id is not None and product_id is not None:
        return _navigation_error(
            400, "ambiguous_param", "only one of category_id or product_id must be provided"
        )
    if category_id is None and product_id is None:
        return _navigation_error(400, "missing_param", "category_id or product_id must be provided")

    try:
        categories = await repository.list_categories()
    except UpstreamServiceError as exc:
        return _upstream_error(exc)

    resolved_via = "category_id" if category_id is not None else "product_id"
    resolved_category_id: UUID
    try:
        if category_id is not None:
            resolved_category_id = UUID(category_id)
        else:
            product_uuid = UUID(product_id or "")
            resolved_category_id = await repository.get_product_category_id(product_uuid)
    except ValueError:
        return _navigation_error(400, "INVALID_REQUEST", "Invalid identifier")
    except UpstreamServiceError as exc:
        if exc.status_code == 404:
            return error_response(404, "NOT_FOUND", "Product not found")
        return _upstream_error(exc)

    try:
        lineage = resolve_lineage(categories, resolved_category_id)
    except CategoryNotFoundError:
        return error_response(404, "NOT_FOUND", "Category not found")
    except OrphanNodeError:
        return _navigation_error(422, "orphan_node", "category hierarchy is broken")

    breadcrumbs = [
        BreadcrumbItemResponse(
            id=node.id,
            slug=_category_slug(node),
            name=node.name,
            url=category_url_path(lineage[: index + 1]),
            level=index,
            is_current=index == len(lineage) - 1,
        )
        for index, node in enumerate(lineage)
    ]
    return BreadcrumbsResponse(
        data=breadcrumbs,
        meta=BreadcrumbMetaResponse(
            resolved_via=resolved_via,
            category_id=resolved_category_id if resolved_via == "category_id" else None,
            product_id=UUID(product_id) if resolved_via == "product_id" and product_id else None,
        ),
    )


@legacy_router.get("/categories/{id}/filters", include_in_schema=False)
async def get_category_filters_alias(
    id: str,
    repository: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> JSONResponse:
    return await get_category_filters(id=id, repository=repository)


def build_category_refs(categories: list[CategoryRecord]) -> list[CategoryRefResponse]:
    by_id = {category.id: category for category in categories}
    return [
        _category_ref_from_lineage(resolve_lineage(by_id, category.id)) for category in categories
    ]


def build_category_tree(categories: list[CategoryRecord]) -> list[CategoryTreeNodeResponse]:
    by_id = {category.id: category for category in categories}
    for category in categories:
        resolve_lineage(by_id, category.id)
    roots = [category for category in categories if category.parent_id is None]
    return [_build_category_tree_node(by_id, root.id) for root in roots]


def resolve_lineage(
    categories: dict[UUID, CategoryRecord] | list[CategoryRecord],
    category_id: UUID,
) -> list[CategoryRecord]:
    by_id = (
        categories
        if isinstance(categories, dict)
        else {category.id: category for category in categories}
    )
    current = by_id.get(category_id)
    if current is None:
        raise CategoryNotFoundError

    lineage: list[CategoryRecord] = []
    seen: set[UUID] = set()
    while current is not None:
        if current.id in seen:
            raise OrphanNodeError
        seen.add(current.id)
        lineage.append(current)
        if current.parent_id is None:
            break
        parent = by_id.get(current.parent_id)
        if parent is None:
            raise OrphanNodeError
        current = parent

    lineage.reverse()
    return lineage


def category_url_path(lineage: list[CategoryRecord]) -> str:
    slugs = [_category_slug(category) for category in lineage]
    return "/catalog/" + "/".join(slugs)


def _category_ref_from_lineage(lineage: list[CategoryRecord]) -> CategoryRefResponse:
    current = lineage[-1]
    return CategoryRefResponse(
        id=current.id,
        name=current.name,
        parent_id=current.parent_id,
        level=len(lineage) - 1,
        path=[category.name for category in lineage],
    )


def _build_category_tree_node(
    by_id: dict[UUID, CategoryRecord],
    category_id: UUID,
) -> CategoryTreeNodeResponse:
    lineage = resolve_lineage(by_id, category_id)
    category = lineage[-1]
    children = [
        _build_category_tree_node(by_id, child.id)
        for child in by_id.values()
        if child.parent_id == category_id
    ]
    return CategoryTreeNodeResponse(
        id=category.id,
        name=category.name,
        parent_id=category.parent_id,
        level=len(lineage) - 1,
        path=[node.name for node in lineage],
        children=children,
    )


async def _load_categories(
    repository: CategoryRepository,
) -> tuple[list[CategoryRecord], JSONResponse | None]:
    try:
        return await repository.list_categories(), None
    except UpstreamServiceError as exc:
        return [], _upstream_error(exc)


async def _fetch_category_filters(category_id: UUID) -> dict[str, Any]:
    import os

    base_url = (os.getenv("B2B_BASE_URL") or "http://localhost:8001").rstrip("/")
    headers: dict[str, str] = {}
    service_key = os.getenv("B2B_SERVICE_KEY")
    if service_key:
        headers["X-Service-Key"] = service_key

    url = f"{base_url}/api/v1/categories/{category_id}/filters"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        raise UpstreamServiceError("Unable to reach B2B", None) from exc

    if response.status_code in {502, 503}:
        raise UpstreamServiceError("B2B temporarily unavailable", response.status_code)
    if response.status_code == 404:
        raise UpstreamServiceError("Category not found", 404)
    if response.status_code != 200:
        raise UpstreamServiceError("Unexpected upstream response", response.status_code)
    return response.json()


def _upstream_error(exc: UpstreamServiceError) -> JSONResponse:
    status_code = 502 if exc.status_code is None else exc.status_code
    return error_response(status_code, "UPSTREAM_UNAVAILABLE", str(exc))


def _navigation_error(status_code: int, code: str, message: str) -> JSONResponse:
    return error_response(status_code, code, message)


def _parse_datetime(value: Any) -> datetime:
    if value is None:
        return datetime.now(UTC)
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _category_slug(category: CategoryRecord) -> str:
    if category.slug:
        return category.slug
    normalized = category.name.strip().lower().replace(" ", "-")
    return "".join(character for character in normalized if character.isalnum() or character == "-")
