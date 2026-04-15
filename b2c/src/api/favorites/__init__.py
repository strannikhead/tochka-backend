from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/favorites", tags=["favorites"])


@router.get("")
async def list_favorites() -> dict[str, str]:
    return {"endpoint": "list_favorites"}


@router.post("/{product_id}")
async def add_to_favorites(product_id: str) -> dict[str, str]:
    return {"endpoint": "add_to_favorites"}


@router.delete("/{product_id}")
async def remove_from_favorites(product_id: str) -> dict[str, str]:
    return {"endpoint": "remove_from_favorites"}


@router.post("/{product_id}/subscribe")
async def subscribe_to_product(product_id: str) -> dict[str, str]:
    return {"endpoint": "subscribe_to_product"}
