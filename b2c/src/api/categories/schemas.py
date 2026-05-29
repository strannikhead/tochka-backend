from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
