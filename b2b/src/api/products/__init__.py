from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.post("")
async def create_product() -> dict[str, str]:
    return {"endpoint": "create_product"}


@router.get("/{id}")
async def get_product(id: str) -> dict[str, str]:
    return {"endpoint": "get_product"}


@router.put("/{id}")
async def update_product(id: str) -> dict[str, str]:
    return {"endpoint": "update_product"}
