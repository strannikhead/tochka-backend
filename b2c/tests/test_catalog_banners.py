from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from src.banners.domain import Banner
from src.banners.repository import InMemoryBannerRepository
from src.main import app

from b2c.src.api.catalog.dependencies import get_banner_repository

BANNER_HIGH = UUID("11111111-1111-1111-1111-111111111111")
BANNER_LOW = UUID("22222222-2222-2222-2222-222222222222")
BANNER_INACTIVE = UUID("33333333-3333-3333-3333-333333333333")
BANNER_EXPIRED = UUID("44444444-4444-4444-4444-444444444444")
BANNER_FUTURE = UUID("55555555-5555-5555-5555-555555555555")


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides = {}


def setup_banner_repository(banners: list[Banner]) -> None:
    app.dependency_overrides[get_banner_repository] = lambda: InMemoryBannerRepository(banners)


def test_active_banners_returned_sorted_by_ordering() -> None:
    now = datetime.now(UTC)
    setup_banner_repository(
        [
            Banner(
                id=BANNER_LOW,
                title="Second",
                image_url="https://cdn.example/second.jpg",
                link="https://example.com/second",
                ordering=20,
                active_from=now - timedelta(days=1),
                active_to=now + timedelta(days=1),
            ),
            Banner(
                id=BANNER_HIGH,
                title="First",
                image_url="https://cdn.example/first.jpg",
                link="https://example.com/first",
                ordering=10,
                active_from=now - timedelta(days=1),
                active_to=now + timedelta(days=1),
            ),
            Banner(
                id=BANNER_INACTIVE,
                title="Inactive",
                image_url="https://cdn.example/inactive.jpg",
                link="https://example.com/inactive",
                ordering=1,
                is_active=False,
            ),
            Banner(
                id=BANNER_EXPIRED,
                title="Expired",
                image_url="https://cdn.example/expired.jpg",
                link="https://example.com/expired",
                ordering=2,
                active_to=now - timedelta(seconds=1),
            ),
            Banner(
                id=BANNER_FUTURE,
                title="Future",
                image_url="https://cdn.example/future.jpg",
                link="https://example.com/future",
                ordering=3,
                active_from=now + timedelta(days=1),
            ),
        ]
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/banners")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(BANNER_HIGH), str(BANNER_LOW)]
    assert [item["ordering"] for item in body] == [10, 20]
    assert body[0]["title"] == "First"
    assert body[0]["image_url"] == "https://cdn.example/first.jpg"
    assert body[0]["link"] == "https://example.com/first"


def test_no_active_banners_returns_200_empty() -> None:
    now = datetime.now(UTC)
    setup_banner_repository(
        [
            Banner(
                id=BANNER_INACTIVE,
                title="Inactive",
                image_url="https://cdn.example/inactive.jpg",
                link="https://example.com/inactive",
                ordering=1,
                is_active=False,
            ),
            Banner(
                id=BANNER_EXPIRED,
                title="Expired",
                image_url="https://cdn.example/expired.jpg",
                link="https://example.com/expired",
                ordering=2,
                active_to=now - timedelta(days=1),
            ),
        ]
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/banners")

    assert response.status_code == 200
    assert response.json() == []
