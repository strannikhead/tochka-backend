from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])


@router.get("")
async def get_categories_tree() -> dict[str, str]:
    return {"endpoint": "get_categories_tree"}


@router.get("/{id}")
async def get_category(id: str) -> dict[str, str]:
    return {"endpoint": "get_category"}


@router.get("/{id}/filters")
async def get_category_filters(id: str) -> dict[str, str]:
    return {"endpoint": "get_category_filters"}
