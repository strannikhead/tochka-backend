from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from src.api.collections.dependencies import (
    get_collection_repository,
    get_collections_b2b_client,
)
from src.api.collections.schemas import CollectionResponse
from src.collections.b2b_client import CollectionsB2BClient, CollectionsB2BError
from src.collections.domain import enrich_collection
from src.collections.repository import CollectionRepository

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/catalog/collections", response_model=None)
async def get_collections(
    repository: Annotated[CollectionRepository, Depends(get_collection_repository)],
    b2b: Annotated[CollectionsB2BClient, Depends(get_collections_b2b_client)],
) -> list[CollectionResponse] | JSONResponse:
    stored = await repository.list_active()

    unique_ids: list[UUID] = []
    seen: set[UUID] = set()
    for collection in stored:
        for pid in collection.product_ids:
            if pid not in seen:
                seen.add(pid)
                unique_ids.append(pid)

    try:
        products_by_id = await b2b.get_products_batch(unique_ids)
    except CollectionsB2BError as exc:
        status_code = exc.status_code or 502
        return JSONResponse(status_code=status_code, content={"message": str(exc)})

    enriched = [enrich_collection(collection, products_by_id) for collection in stored]
    return [CollectionResponse.from_domain(item) for item in enriched]
