from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.products.dependencies import get_product_card_service
from api.products.schemas import ProductResponse
from product_card.repository import UpstreamServiceError
from product_card.service import ProductCardService

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.get("")
async def list_products() -> dict[str, str]:
    return {"endpoint": "list_products"}


@router.get("/{id}", response_model=ProductResponse)
async def get_product(
    id: str,
    service: Annotated[ProductCardService, Depends(get_product_card_service)],
) -> ProductResponse:
    try:
        product_id = UUID(id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id товара") from exc

    try:
        product = await service.get_product_card(product_id)
    except UpstreamServiceError as exc:
        status_code = 502 if exc.status_code is None else exc.status_code
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден")

    return ProductResponse.from_domain(product)


@router.get("/{id}/similar")
async def get_similar_products(id: str) -> dict[str, str]:
    return {"endpoint": "get_similar_products"}


@router.get("/{product_id}/skus")
async def list_product_skus(product_id: str) -> dict[str, str]:
    return {"endpoint": "list_product_skus"}


@router.get("/{product_id}/skus/{sku_id}")
async def get_product_sku(product_id: str, sku_id: str) -> dict[str, str]:
    return {"endpoint": "get_product_sku"}
