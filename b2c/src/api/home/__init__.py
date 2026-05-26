from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from b2c.src.api.catalog.dependencies import get_banner_repository
from b2c.src.api.catalog.schemas import BannerResponse

base = APIRouter()


@base.get("/banners", response_model=list[BannerResponse], response_model_exclude_none=True)
async def get_catalog_banners(
    repository: Annotated[object, Depends(get_banner_repository)],
) -> list[BannerResponse]:
    banners = await repository.list_active(now=datetime.now(UTC))
    return [BannerResponse.from_domain(b) for b in banners]


router = APIRouter(prefix="/api/v1/catalog", tags=["home"])
legacy_router = APIRouter(prefix="/api/v1", tags=["home"], include_in_schema=False)

router.include_router(base)
legacy_router.include_router(base)
