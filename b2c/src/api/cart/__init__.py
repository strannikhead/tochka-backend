from fastapi import APIRouter

router = APIRouter(tags=["cart"])


@router.get("/api/v1/cart")
async def get_cart() -> dict[str, str]:
    return {"endpoint": "get_cart"}


@router.delete("/api/v1/cart")
async def clear_cart() -> dict[str, str]:
    return {"endpoint": "clear_cart"}


@router.post("/api/v1/cart/items")
async def add_cart_item() -> dict[str, str]:
    return {"endpoint": "add_cart_item"}


@router.get("/api/v1/cart/items/{item_id}")
async def get_cart_item(item_id: str) -> dict[str, str]:
    return {"endpoint": "get_cart_item"}


@router.put("/api/v1/cart/items/{item_id}")
async def update_cart_item(item_id: str) -> dict[str, str]:
    return {"endpoint": "update_cart_item"}


@router.delete("/api/v1/cart/items/{item_id}")
async def delete_cart_item(item_id: str) -> dict[str, str]:
    return {"endpoint": "delete_cart_item"}


@router.get("/cart/validate")
async def validate_cart() -> dict[str, str]:
    return {"endpoint": "validate_cart"}


@router.get("/api/v1/cart/also_bought")
async def get_also_bought() -> dict[str, str]:
    return {"endpoint": "get_also_bought"}
