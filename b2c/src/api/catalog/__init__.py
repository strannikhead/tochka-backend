from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/catalog/facets")
async def get_catalog_facets() -> dict[str, str]:
    return {"endpoint": "get_catalog_facets"}


@router.get("/breadcrumbs")
async def get_breadcrumbs() -> dict[str, str]:
    return {"endpoint": "get_breadcrumbs"}
