from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["product-moderation"])


@router.post("/product-moderation/get-next")
async def get_next_for_moderation() -> dict[str, str]:
    return {"endpoint": "get_next_for_moderation"}


@router.post("/products/{id}/approve")
async def approve_product(id: str) -> dict[str, str]:
    return {"endpoint": "approve_product"}


@router.post("/products/{id}/decline")
async def decline_product(id: str) -> dict[str, str]:
    return {"endpoint": "decline_product"}
