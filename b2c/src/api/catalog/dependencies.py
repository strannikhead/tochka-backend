from __future__ import annotations

from src.catalog.repository import CatalogRepository, InMemoryCatalogRepository


def get_catalog_repository() -> CatalogRepository:
    return InMemoryCatalogRepository()
