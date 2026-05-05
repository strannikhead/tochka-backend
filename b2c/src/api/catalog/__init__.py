from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from src.api.catalog.dependencies import get_catalog_repository
from src.api.catalog.filters import parse_filters
from src.api.catalog.schemas import FacetsResponse
from src.catalog.repository import CatalogRepository, UpstreamServiceError

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/catalog/facets", response_model=FacetsResponse)
async def get_catalog_facets(
    request: Request,
    repository: Annotated[CatalogRepository, Depends(get_catalog_repository)],
    category_id: str | None = Query(default=None),
) -> FacetsResponse | JSONResponse:
    if category_id is None:
        return JSONResponse(status_code=400, content={"message": "category_id is required"})
    try:
        category_uuid = UUID(category_id)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid category_id"})

    try:
        filters = parse_filters(request, allow_unscoped=True)
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Invalid filters format"})

    try:
        facets = await repository.get_facets(category_id=category_uuid, filters=filters)
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        return JSONResponse(status_code=status_code, content={"message": str(exc)})

    return FacetsResponse.from_domain(facets)


@router.get("/breadcrumbs")
async def get_breadcrumbs() -> dict[str, str]:
    return {"endpoint": "get_breadcrumbs"}
