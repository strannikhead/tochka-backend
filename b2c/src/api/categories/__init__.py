import os

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from b2c.src.api.catalog.static_data import build_tree
from b2c.src.api.errors import error_response

base = APIRouter()


@base.get("/")
async def get_categories_tree() -> list[dict[str, str]]:
    return build_tree()


@base.get("/{id}")
async def get_category(id: str) -> dict[str, str]:
    # For now return minimal object; can be expanded to call B2B if needed
    return {"id": id}


@base.get("/{id}/filters")
async def get_category_filters(id: str) -> JSONResponse:
    base_url = (os.getenv("B2B_BASE_URL") or "http://localhost:8001").rstrip("/")
    url = f"{base_url}/api/v1/categories/{id}/filters"
    headers = {}
    service_key = os.getenv("B2B_SERVICE_KEY")
    if service_key:
        headers["X-Service-Key"] = service_key

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.RequestError:
        return error_response(502, "Unable to reach B2B", "B2B_UNAVAILABLE")

    try:
        payload = response.json()
    except ValueError:
        payload = {"message": "Unexpected upstream response"}

    if response.status_code != 200:
        # propagate upstream payload but ensure code/message shape when possible
        if isinstance(payload, dict) and ("message" in payload or "code" in payload):
            return JSONResponse(status_code=response.status_code, content=payload)
        return JSONResponse(status_code=response.status_code, content={"message": str(payload)})

    return JSONResponse(content=payload)


router = APIRouter(prefix="/api/v1/catalog/categories", tags=["categories"])
legacy_router = APIRouter(prefix="/api/v1/categories", tags=["categories"], include_in_schema=False)

router.include_router(base)
legacy_router.include_router(base)
