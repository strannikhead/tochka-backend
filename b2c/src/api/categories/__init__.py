import os

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])


@router.get("")
async def get_categories_tree() -> dict[str, str]:
    return {"endpoint": "get_categories_tree"}


@router.get("/{id}")
async def get_category(id: str) -> dict[str, str]:
    return {"endpoint": "get_category"}


@router.get("/{id}/filters")
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
        return JSONResponse(status_code=502, content={"message": "Unable to reach B2B"})

    try:
        payload = response.json()
    except ValueError:
        payload = {"message": "Unexpected upstream response"}

    if response.status_code != 200:
        return JSONResponse(status_code=response.status_code, content=payload)

    return JSONResponse(content=payload)
