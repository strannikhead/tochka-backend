from __future__ import annotations

from uuid import UUID

import pytest

from b2c.src.catalog import repository as catalog_repository


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.status_code = 200
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, params=None, headers=None) -> _FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self._response


@pytest.mark.asyncio
async def test_http_catalog_repository_translates_request_and_response(monkeypatch) -> None:
    payload = {
        "items": [
            {
                "id": "770e8400-e29b-41d4-a716-446655441001",
                "name": "iPhone 15",
                "min_price": 12999000,
                "has_stock": True,
                "images": [
                    {
                        "id": "770e8400-e29b-41d4-a716-446655441002",
                        "url": "https://example.com/image.jpg",
                        "ordering": 0,
                    }
                ],
                "status": "MODERATED",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ],
        "total_count": 1,
        "limit": 20,
        "offset": 0,
    }
    fake_response = _FakeResponse(payload)
    fake_client = _FakeAsyncClient(fake_response)
    monkeypatch.setattr(catalog_repository.httpx, "AsyncClient", lambda timeout: fake_client)

    repository = catalog_repository.HttpCatalogRepository(
        base_url="https://b2b.example", service_key="secret"
    )
    result = await repository.list_products(
        category_id=UUID("123e4567-e89b-12d3-a456-426614174001"),
        filters={"brand": ["Apple"]},
        sort="new",
        limit=20,
        offset=0,
        search="wireless",
        min_price=1000,
        max_price=5000,
    )

    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["url"] == "https://b2b.example/api/v1/public/products"
    assert ("search", "wireless") in call["params"]
    assert ("sort", "created_desc") in call["params"]
    assert ("min_price", "1000") in call["params"]
    assert ("max_price", "5000") in call["params"]
    assert ("filters[brand]", "Apple") in call["params"]
    assert call["headers"] == {"X-Service-Key": "secret"}

    assert result.total_count == 1
    assert result.items[0].title == "iPhone 15"
    assert result.items[0].image == "https://example.com/image.jpg"
    assert result.items[0].price == 12999000
    assert result.items[0].in_stock is True
