from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/skus", tags=["skus"])


@router.post("")
async def create_sku() -> dict[str, str]:
    return {"endpoint": "create_sku"}


@router.put("")
async def update_sku() -> dict[str, str]:
    return {"endpoint": "update_sku"}
