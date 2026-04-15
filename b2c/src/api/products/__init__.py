from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.get("")
async def list_products() -> dict[str, str]:
    return {"endpoint": "list_products"}


@router.get("/{id}")
async def get_product(id: str) -> dict[str, str]:
    return {"endpoint": "get_product"}


@router.get("/{id}/similar")
async def get_similar_products(id: str) -> dict[str, str]:
    return {"endpoint": "get_similar_products"}


@router.get("/{product_id}/skus")
async def list_product_skus(product_id: str) -> dict[str, str]:
    return {"endpoint": "list_product_skus"}


@router.get("/{product_id}/skus/{sku_id}")
async def get_product_sku(product_id: str, sku_id: str) -> dict[str, str]:
    return {"endpoint": "get_product_sku"}
