from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.post("")
async def create_product() -> dict[str, str]:
    return {"endpoint": "create_product"}


@router.get("/{id}")
async def get_product(id: str):
    try:
        product_id = UUID(id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный id товара") from exc

    if str(product_id) == "770e8400-e29b-41d4-a716-446655440099":
        raise HTTPException(status_code=404, detail="Товар не найден")

    return JSONResponse(
        content={
            "id": str(product_id),
            "slug": "iphone-15-pro-max",
            "title": "iPhone 15 Pro Max",
            "description": "Флагманский смартфон Apple 2024 года с чипом A17 Pro",
            "images": [
                {
                    "url": "https://images.steamusercontent.com/ugc/1248008971461813591/136B1A9E56BD56F0453117B4561B1B942AC93024/?imw=512&amp;&amp;ima=fit&amp;impolicy=Letterbox&amp;imcolor=%23000000&amp;letterbox=false",
                    "ordering": 0,
                },
                {
                    "url": "https://i.pinimg.com/736x/a6/f9/e9/a6f9e975d2cae3463d66d7a40a6cfe23.jpg",
                    "ordering": 1,
                },
            ],
            "status": "MODERATED",
            "characteristics": [
                {"name": "Бренд", "value": "Apple"},
                {"name": "Страна-производитель", "value": "Китай"},
            ],
            "skus": [
                {
                    "id": "660e8400-e29b-41d4-a716-446655440001",
                    "name": "256GB Black",
                    "price": 12999000,
                    "discount": 0,
                    "image": "/s3/iphone15-black-256.jpg",
                    "active_quantity": 10,
                    "cost_price": 9990000,
                    "reserved_quantity": 2,
                    "characteristics": [
                        {"name": "Цвет", "value": "Чёрный"},
                        {"name": "Объём памяти", "value": "256 ГБ"},
                    ],
                },
                {
                    "id": "660e8400-e29b-41d4-a716-446655440002",
                    "name": "256GB White",
                    "price": 12999000,
                    "discount": 500000,
                    "image": "/s3/iphone15-white-256.jpg",
                    "active_quantity": 0,
                    "cost_price": 9990000,
                    "reserved_quantity": 0,
                    "characteristics": [
                        {"name": "Цвет", "value": "Белый"},
                        {"name": "Объём памяти", "value": "256 ГБ"},
                    ],
                },
            ],
        }
    )


@router.put("/{id}")
async def update_product(id: str) -> dict[str, str]:
    return {"endpoint": "update_product"}
