"""Canonical apply-moderation flow for US-B2B-09 (POST /api/v1/moderation/events).

Behaviour follows b2b/openapi.yaml:
  * path is /api/v1/moderation/events, auth via X-Service-Key, success/duplicate -> 204;
  * MODERATED clears blocking data; BLOCKED saves field_reports; hard_block -> HARD_BLOCKED;
  * BLOCKED cascades PRODUCT_BLOCKED to B2C when there is active stock;
  * idempotent by (sender_service, idempotency_key): a duplicate event has no side effects.

Integration style (real async engine) mirrors test_products_edit.py; needs `aiosqlite`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from b2b.src.auth import get_current_seller_id
from b2b.src.db import SessionLocal
from b2b.src.main import app
from b2b.src.models import (
    SKU,
    Base,
    Category,
    OutboxEvent,
    ProcessedEvent,
    Product,
    ProductStatus,
)

SELLER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
CATEGORY_ID = UUID("550e8400-e29b-41d4-a716-446655440010")
REASON_ID = UUID("660e8400-e29b-41d4-a716-446655440010")
SERVICE_HEADERS = {"X-Service-Key": "dev-service-key"}


class DbState:
    def __init__(self, engine, session_factory, products: dict[str, UUID]):
        self.engine = engine
        self.session_factory = session_factory
        self.products = products


def _active_sku(product_id: UUID) -> SKU:
    now = datetime.now(UTC)
    return SKU(
        id=uuid4(),
        product_id=product_id,
        name="SKU",
        price=12999000,
        discount=0,
        cost_price=9990000,
        stock_quantity=12,
        active_quantity=10,
        reserved_quantity=2,
        article=f"ART-{uuid4().hex[:8]}",
        images=[],
        characteristics=[],
        created_at=now,
        updated_at=now,
    )


def _product(*, title: str, status: ProductStatus, blocked: bool = False) -> Product:
    now = datetime.now(UTC)
    product = Product(
        id=uuid4(),
        seller_id=SELLER_ID,
        title=title,
        slug=title.lower().replace(" ", "-"),
        description="desc",
        status=status,
        category_id=CATEGORY_ID,
        images=[],
        characteristics=[],
        blocking_reason_id=REASON_ID if blocked else None,
        moderator_comment="old comment" if blocked else None,
        field_reports=[{"field_name": "title", "comment": "old", "sku_id": None}]
        if blocked
        else [],
        created_at=now,
        updated_at=now,
    )
    product.skus = [_active_sku(product.id)]
    return product


@pytest.fixture()
def db_state(tmp_path: Path) -> Generator[DbState]:
    db_path = tmp_path / "b2b.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> dict[str, UUID]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        now = datetime.now(UTC)
        ids: dict[str, UUID] = {}
        async with session_factory() as session:
            session.add(
                Category(
                    id=CATEGORY_ID,
                    name="Phones",
                    parent_id=None,
                    level=0,
                    path="/phones",
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            blocked = _product(title="Blocked", status=ProductStatus.BLOCKED, blocked=True)
            moderated = _product(title="Moderated", status=ProductStatus.MODERATED)
            hard = _product(title="Hard", status=ProductStatus.HARD_BLOCKED)
            session.add_all([blocked, moderated, hard])
            await session.commit()
            ids = {"blocked": blocked.id, "moderated": moderated.id, "hard": hard.id}
        return ids

    ids = asyncio.run(prepare())
    state = DbState(engine, session_factory, ids)

    import b2b.src.db as db_module

    original_session_local = SessionLocal
    db_module.SessionLocal = session_factory
    app.dependency_overrides = {}
    app.dependency_overrides[get_current_seller_id] = lambda: SELLER_ID
    try:
        yield state
    finally:
        app.dependency_overrides = {}
        db_module.SessionLocal = original_session_local
        asyncio.run(engine.dispose())


@pytest.fixture()
def client(db_state: DbState) -> Generator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _event(product_id: UUID, event_type: str, **extra: object) -> dict[str, object]:
    body: dict[str, object] = {
        "idempotency_key": str(uuid4()),
        "product_id": str(product_id),
        "event_type": event_type,
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    body.update(extra)
    return body


async def _fetch_product(session_factory, product_id: UUID) -> Product | None:
    async with session_factory() as session:
        return await session.get(Product, product_id)


async def _fetch_outbox(session_factory, event_type: str) -> list[OutboxEvent]:
    async with session_factory() as session:
        result = await session.execute(
            select(OutboxEvent).where(OutboxEvent.event_type == event_type)
        )
        return list(result.scalars().all())


async def _count_processed(session_factory) -> int:
    async with session_factory() as session:
        result = await session.execute(select(ProcessedEvent))
        return len(list(result.scalars().all()))


def test_moderated_event_clears_blocking_data(client: TestClient, db_state: DbState) -> None:
    product_id = db_state.products["blocked"]

    response = client.post(
        "/api/v1/moderation/events",
        json=_event(product_id, "MODERATED"),
        headers=SERVICE_HEADERS,
    )

    assert response.status_code == 204
    product = asyncio.run(_fetch_product(db_state.session_factory, product_id))
    assert product is not None
    assert product.status == ProductStatus.MODERATED
    assert product.blocking_reason_id is None
    assert product.moderator_comment is None
    assert product.field_reports == []


def test_blocked_soft_saves_field_reports(client: TestClient, db_state: DbState) -> None:
    product_id = db_state.products["moderated"]
    reports = [{"field_name": "title", "comment": "Misleading", "sku_id": None}]

    response = client.post(
        "/api/v1/moderation/events",
        json=_event(
            product_id,
            "BLOCKED",
            hard_block=False,
            blocking_reason_id=str(REASON_ID),
            moderator_comment="Fix the title",
            field_reports=reports,
        ),
        headers=SERVICE_HEADERS,
    )

    assert response.status_code == 204
    product = asyncio.run(_fetch_product(db_state.session_factory, product_id))
    assert product is not None
    assert product.status == ProductStatus.BLOCKED
    assert product.field_reports == reports
    # Cascade to B2C because the product has active stock.
    cascades = asyncio.run(_fetch_outbox(db_state.session_factory, "PRODUCT_BLOCKED"))
    assert len(cascades) == 1
    assert cascades[0].payload["product_id"] == str(product_id)


def test_blocked_hard_sets_terminal_status(client: TestClient, db_state: DbState) -> None:
    product_id = db_state.products["moderated"]

    response = client.post(
        "/api/v1/moderation/events",
        json=_event(
            product_id,
            "BLOCKED",
            hard_block=True,
            blocking_reason_id=str(REASON_ID),
            moderator_comment="Prohibited goods",
        ),
        headers=SERVICE_HEADERS,
    )

    assert response.status_code == 204
    product = asyncio.run(_fetch_product(db_state.session_factory, product_id))
    assert product is not None
    assert product.status == ProductStatus.HARD_BLOCKED
    cascades = asyncio.run(_fetch_outbox(db_state.session_factory, "PRODUCT_BLOCKED"))
    assert len(cascades) == 1
    assert cascades[0].payload["hard_block"] is True


def test_hard_blocked_product_rejects_seller_edits(client: TestClient, db_state: DbState) -> None:
    hard_id = db_state.products["hard"]

    patch_response = client.patch(f"/api/v1/products/{hard_id}", json={"title": "New title"})
    delete_response = client.delete(f"/api/v1/products/{hard_id}")

    assert patch_response.status_code == 403
    assert delete_response.status_code == 403


def test_duplicate_event_same_idempotency_key_no_side_effects(
    client: TestClient, db_state: DbState
) -> None:
    product_id = db_state.products["moderated"]
    event = _event(
        product_id,
        "BLOCKED",
        hard_block=False,
        blocking_reason_id=str(REASON_ID),
        moderator_comment="Fix the title",
        field_reports=[{"field_name": "title", "comment": "Misleading", "sku_id": None}],
    )

    first = client.post("/api/v1/moderation/events", json=event, headers=SERVICE_HEADERS)
    second = client.post("/api/v1/moderation/events", json=event, headers=SERVICE_HEADERS)

    assert first.status_code == 204
    assert second.status_code == 204
    # Exactly one processed-event row and one cascade — the replay changed nothing.
    assert asyncio.run(_count_processed(db_state.session_factory)) == 1
    cascades = asyncio.run(_fetch_outbox(db_state.session_factory, "PRODUCT_BLOCKED"))
    assert len(cascades) == 1


def test_missing_service_key_returns_401(client: TestClient, db_state: DbState) -> None:
    product_id = db_state.products["moderated"]

    response = client.post("/api/v1/moderation/events", json=_event(product_id, "MODERATED"))

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
