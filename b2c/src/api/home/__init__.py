from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["home"])


@router.get("/home/banners")
async def get_home_banners() -> dict[str, str]:
    return {"endpoint": "get_home_banners"}


@router.post("/banner-events")
async def post_banner_events() -> dict[str, str]:
    return {"endpoint": "post_banner_events"}


@router.get("/main/collections")
async def get_collections() -> dict[str, str]:
    return {"endpoint": "get_collections"}


@router.get("/collections/{collection_id}/products")
async def get_collection_products(collection_id: str) -> dict[str, str]:
    return {"endpoint": "get_collection_products"}
