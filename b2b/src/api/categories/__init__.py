from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])

_CATEGORY_FILTERS: dict[UUID, list[dict[str, object]]] = {
    UUID("2c4e1c32-9e37-4c86-9e5a-0d3a6fa3b4c1"): [
        {"name": "brand", "values": ["Apple", "Samsung", "Google"]},
        {"name": "color", "values": ["Black", "Silver", "Gray", "White"]},
        {"name": "memory", "values": ["128", "256"]},
    ]
}


@router.get("/{id}/filters")
async def get_category_filters(id: str) -> JSONResponse:
    try:
        category_id = UUID(id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id категории") from exc

    filters = _CATEGORY_FILTERS.get(category_id)
    if filters is None:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    return JSONResponse(content={"category_id": str(category_id), "filters": filters})


@router.get("")
async def list_categories(parent_id: str | None = None, only_root: bool = False):
    return JSONResponse(content=[])


@router.post("")
async def create_category() -> JSONResponse:
    return JSONResponse(status_code=201, content={})


@router.get("/tree")
async def get_categories_tree():
    return JSONResponse(content=[])


@router.get("/{category_id}")
async def get_category(category_id: str) -> JSONResponse:
    return JSONResponse(content={})


@router.patch("/{category_id}")
async def update_category(category_id: str) -> JSONResponse:
    return JSONResponse(content={})


@router.delete("/{category_id}")
async def delete_category(category_id: str):
    return JSONResponse(status_code=204, content=None)


@router.get("/{category_id}/breadcrumbs")
async def get_category_breadcrumbs(category_id: str) -> JSONResponse:
    return JSONResponse(content=[])
