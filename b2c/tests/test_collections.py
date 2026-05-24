from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from src.api.collections.dependencies import (
    get_collection_repository,
    get_collections_b2b_client,
)
from src.collections.b2b_client import InMemoryCollectionsB2BClient
from src.collections.domain import B2BProductCard, B2BProductImage, CollectionStored
from src.collections.repository import InMemoryCollectionRepository
from src.main import app

COLLECTION_HITS = UUID("11111111-1111-1111-1111-111111111111")
COLLECTION_NEW = UUID("22222222-2222-2222-2222-222222222222")

PRODUCT_AVAILABLE_1 = UUID("aaaaaaaa-1111-1111-1111-111111111111")
PRODUCT_AVAILABLE_2 = UUID("aaaaaaaa-2222-2222-2222-222222222222")
PRODUCT_DELETED = UUID("dddddddd-1111-1111-1111-111111111111")
PRODUCT_BLOCKED = UUID("bbbbbbbb-1111-1111-1111-111111111111")


def make_product(
    product_id: UUID,
    *,
    name: str = "Sample",
    min_price: int = 9990,
    has_stock: bool = True,
    slug: str | None = "sample",
) -> B2BProductCard:
    return B2BProductCard(
        id=product_id,
        name=name,
        slug=slug,
        min_price=min_price,
        has_stock=has_stock,
        images=(
            B2BProductImage(
                id=product_id,
                url=f"https://cdn.example/{product_id}.jpg",
                ordering=0,
                is_main=True,
            ),
        ),
    )


def setup_overrides(
    repo: InMemoryCollectionRepository,
    b2b: InMemoryCollectionsB2BClient,
) -> None:
    app.dependency_overrides[get_collection_repository] = lambda: repo
    app.dependency_overrides[get_collections_b2b_client] = lambda: b2b


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides = {}


def test__collections_list_returns_metadata_and_products() -> None:
    repo = InMemoryCollectionRepository(
        collections=[
            CollectionStored(
                id=COLLECTION_HITS,
                name="Хиты продаж",
                description="Самое популярное",
                product_ids=(PRODUCT_AVAILABLE_1, PRODUCT_AVAILABLE_2),
                ordering=0,
            ),
            CollectionStored(
                id=COLLECTION_NEW,
                name="Новинки сезона",
                description=None,
                product_ids=(PRODUCT_AVAILABLE_2,),
                ordering=1,
            ),
        ]
    )
    b2b = InMemoryCollectionsB2BClient(
        products={
            PRODUCT_AVAILABLE_1: make_product(PRODUCT_AVAILABLE_1, name="iPhone"),
            PRODUCT_AVAILABLE_2: make_product(PRODUCT_AVAILABLE_2, name="Galaxy"),
        }
    )
    setup_overrides(repo, b2b)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/collections")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert [c["id"] for c in body] == [str(COLLECTION_HITS), str(COLLECTION_NEW)]

    hits = body[0]
    assert hits["name"] == "Хиты продаж"
    assert hits["description"] == "Самое популярное"
    assert [p["id"] for p in hits["products"]] == [
        str(PRODUCT_AVAILABLE_1),
        str(PRODUCT_AVAILABLE_2),
    ]
    assert hits["products"][0]["name"] == "iPhone"
    assert hits["products"][0]["has_stock"] is True
    assert hits["products"][0]["images"][0]["url"].endswith(f"{PRODUCT_AVAILABLE_1}.jpg")


def test__collection_products_enriched_from_b2b() -> None:
    repo = InMemoryCollectionRepository(
        collections=[
            CollectionStored(
                id=COLLECTION_HITS,
                name="Хиты продаж",
                description=None,
                product_ids=(PRODUCT_AVAILABLE_1,),
                ordering=0,
            )
        ]
    )
    b2b = InMemoryCollectionsB2BClient(
        products={
            PRODUCT_AVAILABLE_1: make_product(
                PRODUCT_AVAILABLE_1,
                name="iPhone 15",
                min_price=12999000,
                has_stock=True,
                slug="iphone-15",
            )
        }
    )
    setup_overrides(repo, b2b)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/collections")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    product = body[0]["products"][0]
    assert product == {
        "id": str(PRODUCT_AVAILABLE_1),
        "name": "iPhone 15",
        "slug": "iphone-15",
        "min_price": 12999000,
        "has_stock": True,
        "images": [
            {
                "id": str(PRODUCT_AVAILABLE_1),
                "url": f"https://cdn.example/{PRODUCT_AVAILABLE_1}.jpg",
                "ordering": 0,
                "is_main": True,
            }
        ],
    }


def test__unavailable_products_are_filtered_out() -> None:
    repo = InMemoryCollectionRepository(
        collections=[
            CollectionStored(
                id=COLLECTION_HITS,
                name="Хиты продаж",
                description=None,
                product_ids=(
                    PRODUCT_AVAILABLE_1,
                    PRODUCT_DELETED,
                    PRODUCT_BLOCKED,
                    PRODUCT_AVAILABLE_2,
                ),
                ordering=0,
            )
        ]
    )
    b2b = InMemoryCollectionsB2BClient(
        products={
            PRODUCT_AVAILABLE_1: make_product(PRODUCT_AVAILABLE_1),
            PRODUCT_AVAILABLE_2: make_product(PRODUCT_AVAILABLE_2),
        }
    )
    setup_overrides(repo, b2b)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/collections")

    assert response.status_code == 200
    body = response.json()
    products = body[0]["products"]
    returned_ids = [p["id"] for p in products]
    assert returned_ids == [str(PRODUCT_AVAILABLE_1), str(PRODUCT_AVAILABLE_2)]
    assert str(PRODUCT_DELETED) not in returned_ids
    assert str(PRODUCT_BLOCKED) not in returned_ids


def test__none_optionals_are_omitted_from_response() -> None:
    repo = InMemoryCollectionRepository(
        collections=[
            CollectionStored(
                id=COLLECTION_HITS,
                name="Хиты продаж",
                description=None,
                product_ids=(PRODUCT_AVAILABLE_1,),
                ordering=0,
            )
        ]
    )
    b2b = InMemoryCollectionsB2BClient(
        products={PRODUCT_AVAILABLE_1: make_product(PRODUCT_AVAILABLE_1, slug=None)}
    )
    setup_overrides(repo, b2b)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/collections")

    assert response.status_code == 200
    body = response.json()
    assert "description" not in body[0]
    assert "slug" not in body[0]["products"][0]


def test__all_products_unavailable_returns_empty_products() -> None:
    repo = InMemoryCollectionRepository(
        collections=[
            CollectionStored(
                id=COLLECTION_HITS,
                name="Хиты продаж",
                description=None,
                product_ids=(PRODUCT_DELETED, PRODUCT_BLOCKED),
                ordering=0,
            )
        ]
    )
    b2b = InMemoryCollectionsB2BClient(products={})
    setup_overrides(repo, b2b)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/collections")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["products"] == []


def test__empty_collections_returns_empty_list() -> None:
    repo = InMemoryCollectionRepository(collections=[])
    b2b = InMemoryCollectionsB2BClient(products={})
    setup_overrides(repo, b2b)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/collections")

    assert response.status_code == 200
    assert response.json() == []


def test__batch_b2b_call_deduplicates_product_ids_across_collections() -> None:
    seen_calls: list[list[UUID]] = []

    class RecordingClient(InMemoryCollectionsB2BClient):
        async def get_products_batch(self, product_ids: list[UUID]) -> dict[UUID, B2BProductCard]:
            seen_calls.append(list(product_ids))
            return await super().get_products_batch(product_ids)

    repo = InMemoryCollectionRepository(
        collections=[
            CollectionStored(
                id=COLLECTION_HITS,
                name="Хиты",
                description=None,
                product_ids=(PRODUCT_AVAILABLE_1, PRODUCT_AVAILABLE_2),
                ordering=0,
            ),
            CollectionStored(
                id=COLLECTION_NEW,
                name="Новинки",
                description=None,
                product_ids=(PRODUCT_AVAILABLE_1,),
                ordering=1,
            ),
        ]
    )
    b2b = RecordingClient(
        products={
            PRODUCT_AVAILABLE_1: make_product(PRODUCT_AVAILABLE_1),
            PRODUCT_AVAILABLE_2: make_product(PRODUCT_AVAILABLE_2),
        }
    )
    setup_overrides(repo, b2b)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/collections")

    assert response.status_code == 200
    assert len(seen_calls) == 1
    assert seen_calls[0] == [PRODUCT_AVAILABLE_1, PRODUCT_AVAILABLE_2]


def test__b2b_only_called_once_with_uuid_list_param_types() -> None:
    repo = InMemoryCollectionRepository(
        collections=[
            CollectionStored(
                id=COLLECTION_HITS,
                name="Хиты",
                description=None,
                product_ids=(PRODUCT_AVAILABLE_1,),
                ordering=0,
            )
        ]
    )
    received: list[list[UUID]] = []

    class TypeCheckingClient(InMemoryCollectionsB2BClient):
        async def get_products_batch(self, product_ids: list[UUID]) -> dict[UUID, B2BProductCard]:
            received.append(product_ids)
            return await super().get_products_batch(product_ids)

    b2b = TypeCheckingClient(products={PRODUCT_AVAILABLE_1: make_product(PRODUCT_AVAILABLE_1)})
    setup_overrides(repo, b2b)

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/collections")

    assert response.status_code == 200
    assert len(received) == 1
    assert all(isinstance(pid, UUID) for pid in received[0])
