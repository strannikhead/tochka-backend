from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/skus", tags=["skus"])


@router.post("")
async def create_sku() -> dict[str, str]:
    return {"endpoint": "create_sku"}


@router.get("/{sku_id}")
async def get_sku(sku_id: str) -> dict[str, str]:
    return {"endpoint": "get_sku"}


@router.patch("/{sku_id}")
async def update_sku(sku_id: str) -> dict[str, str]:
    return {"endpoint": "update_sku"}


@router.delete("/{sku_id}")
async def delete_sku(sku_id: str) -> dict[str, str]:
    return {"endpoint": "delete_sku"}


@router.post("/images")
async def add_sku_image() -> dict[str, str]:
    return {"endpoint": "add_sku_image"}


@router.patch("/images/{image_id}")
async def update_sku_image(image_id: str) -> dict[str, str]:
    return {"endpoint": "update_sku_image"}


@router.delete("/images/{image_id}")
async def delete_sku_image(image_id: str) -> dict[str, str]:
    return {"endpoint": "delete_sku_image"}
