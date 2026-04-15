from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/product-blocking-reasons", tags=["blocking-reasons"])


@router.get("")
async def get_blocking_reasons() -> dict[str, str]:
    return {"endpoint": "get_blocking_reasons"}
