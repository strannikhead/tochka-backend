from __future__ import annotations

from b2c.src.catalog.repository import CatalogRepository, HttpCatalogRepository


def get_catalog_repository() -> CatalogRepository:
    return HttpCatalogRepository()
