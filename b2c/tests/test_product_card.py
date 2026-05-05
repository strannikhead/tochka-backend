from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from src.api.products.dependencies import get_product_repository
from src.main import app
from src.product_card.domain import Characteristic, Image, Product, ProductStatus, Sku
from src.product_card.repository import ProductRepository

PRODUCT_ID = UUID("770e8400-e29b-41d4-a716-446655440002")
BLOCKED_PRODUCT_ID = UUID("770e8400-e29b-41d4-a716-446655440099")


class StubProductRepository(ProductRepository):
    def __init__(self, products: dict[UUID, Product]) -> None:
        self._products = products

    async def get_product(self, product_id: UUID) -> Product | None:
        return self._products.get(product_id)


@pytest.fixture()
def client() -> Generator[TestClient]:
    app.dependency_overrides = {}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


def build_product(
    product_id: UUID, status: ProductStatus, sku_quantities: tuple[int, int]
) -> Product:
    images = (Image(url="https://example.com/images/iphone14.jpg", order=1),)
    characteristics = (
        Characteristic(name="BRAND", value="Apple"),
        Characteristic(name="COLOR", value="Silver"),
    )
    skus = (
        Sku(
            id=UUID("660e8400-e29b-41d4-a716-446655440001"),
            name="iPhone 14 Pro 128GB Silver",
            price=99999,
            discount=0,
            quantity=sku_quantities[0],
            characteristics=(
                Characteristic(name="COLOR", value="Silver"),
                Characteristic(name="MEMORY", value="128GB"),
            ),
            images=(Image(url="https://example.com/images/sku1.jpg", order=1),),
        ),
        Sku(
            id=UUID("660e8400-e29b-41d4-a716-446655440002"),
            name="iPhone 14 Pro 256GB Gold",
            price=109999,
            discount=5000,
            quantity=sku_quantities[1],
            characteristics=(
                Characteristic(name="COLOR", value="Gold"),
                Characteristic(name="MEMORY", value="256GB"),
            ),
            images=(Image(url="https://example.com/images/sku2.jpg", order=1),),
        ),
    )
    return Product(
        id=product_id,
        slug="iphone-14-pro",
        title="iPhone 14 Pro",
        description="Смартфон Apple iPhone 14 Pro с диагональю 6.1 дюйма",
        images=images,
        status=status,
        characteristics=characteristics,
        skus=skus,
    )


def override_repository(product: Product) -> None:
    repository = StubProductRepository({product.id: product})
    app.dependency_overrides[get_product_repository] = lambda: repository


def test__get_sku__product_card_returns_full_data_with_skus(client: TestClient) -> None:
    product = build_product(PRODUCT_ID, ProductStatus.MODERATED, (12, 3))
    override_repository(product)

    response = client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(product.id)
    assert payload["description"] == product.description
    assert payload["images"]
    assert len(payload["skus"]) == 2
    assert payload["skus"][0]["price"] == product.skus[0].price
    assert "in_stock" in payload["skus"][0]


@pytest.mark.parametrize("bad_word", ["cost_price", "reserved_quantity"])
def test__get_sku__cost_price_absent_in_response(client: TestClient, bad_word: str) -> None:
    product = build_product(PRODUCT_ID, ProductStatus.MODERATED, (12, 3))
    override_repository(product)

    response = client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 200
    payload = response.json()
    assert bad_word not in payload["skus"][0]


def test__get_sku__blocked_product_returns_404(client: TestClient) -> None:
    product = build_product(BLOCKED_PRODUCT_ID, ProductStatus.BLOCKED, (12, 3))
    override_repository(product)

    response = client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 404


def test__get_sku__sku_without_stock_is_shown_as_unavailable(client: TestClient) -> None:
    product = build_product(PRODUCT_ID, ProductStatus.MODERATED, (12, 0))
    override_repository(product)

    response = client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 200
    payload = response.json()
    sku_without_stock = next(sku for sku in payload["skus"] if sku["quantity"] == 0)
    assert sku_without_stock["in_stock"] is False
