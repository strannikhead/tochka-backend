from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from db import get_session  # noqa: E402
from main import app  # noqa: E402
from models import (  # noqa: E402
    B2BEventType,
    Base,
    FieldReport,
    FieldReportSeverity,
    ProcessedB2BEvent,
    ProductModeration,
    TicketKind,
    TicketStatus,
)

SERVICE_HEADERS = {"X-Service-Key": "dev-b2b-to-mod-key"}
SELLER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
CATEGORY_ID = UUID("550e8400-e29b-41d4-a716-446655440010")
MODERATOR_ID = UUID("550e8400-e29b-41d4-a716-446655440020")


@dataclass
class DbState:
    engine: object
    session_factory: async_sessionmaker


@pytest.fixture()
def db_state(tmp_path: Path) -> Generator[DbState]:
    db_path = tmp_path / "moderation.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(prepare())

    async def override_get_session() -> AsyncGenerator:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    state = DbState(engine=engine, session_factory=session_factory)
    try:
        yield state
    finally:
        app.dependency_overrides = {}
        asyncio.run(engine.dispose())


@pytest.fixture()
def client(db_state: DbState) -> Generator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _event(
    event_type: str, payload: dict[str, object], *, idempotency_key: UUID | None = None
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "idempotency_key": str(idempotency_key or uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        "payload": payload,
    }


def _created_payload(product_id: UUID, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "product_id": str(product_id),
        "seller_id": str(SELLER_ID),
        "category_id": str(CATEGORY_ID),
        "json_after": {"title": "Phone", "total_active_quantity": 5},
    }
    payload.update(extra)
    return payload


def _edited_payload(product_id: UUID, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "product_id": str(product_id),
        "seller_id": str(SELLER_ID),
        "category_id": str(CATEGORY_ID),
        "json_before": {"title": "Old phone", "total_active_quantity": 1},
        "json_after": {"title": "New phone", "total_active_quantity": 3},
    }
    payload.update(extra)
    return payload


async def _fetch_ticket(
    session_factory: async_sessionmaker, product_id: UUID
) -> ProductModeration | None:
    async with session_factory() as session:
        result = await session.execute(
            select(ProductModeration).where(ProductModeration.product_id == product_id)
        )
        return result.scalar_one_or_none()


async def _count_processed(session_factory: async_sessionmaker) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count(ProcessedB2BEvent.id))) or 0


async def _insert_processed_event(
    session_factory: async_sessionmaker,
    *,
    idempotency_key: UUID,
    product_id: UUID,
    processed_at: datetime,
) -> None:
    async with session_factory() as session:
        session.add(
            ProcessedB2BEvent(
                idempotency_key=idempotency_key,
                event_type=B2BEventType.PRODUCT_CREATED,
                product_id=product_id,
                occurred_at=processed_at,
                processed_at=processed_at,
            )
        )
        await session.commit()


async def _count_field_reports(session_factory: async_sessionmaker) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count(FieldReport.id))) or 0


async def _insert_ticket(
    session_factory: async_sessionmaker,
    *,
    product_id: UUID,
    status: TicketStatus,
    kind: TicketKind = TicketKind.CREATE,
    queue_priority: int = 3,
    with_report: bool = False,
) -> None:
    async with session_factory() as session:
        ticket = ProductModeration(
            product_id=product_id,
            seller_id=SELLER_ID,
            category_id=CATEGORY_ID,
            kind=kind.value,
            status=status.value,
            queue_priority=queue_priority,
            moderator_id=MODERATOR_ID if status == TicketStatus.IN_REVIEW else None,
            claimed_at=datetime.now(UTC) if status == TicketStatus.IN_REVIEW else None,
            claim_expires_at=datetime.now(UTC) if status == TicketStatus.IN_REVIEW else None,
            date_moderation=datetime.now(UTC)
            if status in {TicketStatus.APPROVED, TicketStatus.BLOCKED}
            else None,
            moderator_comment="old decision",
            json_before={"title": "before"} if kind == TicketKind.EDIT else None,
            json_after={"title": "current", "total_active_quantity": 1},
        )
        session.add(ticket)
        await session.flush()
        if with_report:
            session.add(
                FieldReport(
                    ticket_id=ticket.id,
                    field_path="title",
                    message="old problem",
                    severity=FieldReportSeverity.ERROR,
                )
            )
        await session.commit()


def test_created_pending(client: TestClient, db_state: DbState) -> None:
    product_id = uuid4()

    response = client.post(
        "/api/v1/b2b/events",
        json=_event("PRODUCT_CREATED", _created_payload(product_id, queue_priority=1)),
        headers=SERVICE_HEADERS,
    )

    assert response.status_code == 202
    assert response.content == b""
    ticket = asyncio.run(_fetch_ticket(db_state.session_factory, product_id))
    assert ticket is not None
    assert ticket.product_id == product_id
    assert ticket.seller_id == SELLER_ID
    assert ticket.category_id == CATEGORY_ID
    assert ticket.kind == TicketKind.CREATE.value
    assert ticket.status == TicketStatus.PENDING.value
    assert ticket.queue_priority == 1
    assert ticket.json_before is None
    assert ticket.json_after["title"] == "Phone"
    assert asyncio.run(_count_processed(db_state.session_factory)) == 1


def test_edited_returns_to_review(client: TestClient, db_state: DbState) -> None:
    product_id = uuid4()
    asyncio.run(
        _insert_ticket(
            db_state.session_factory,
            product_id=product_id,
            status=TicketStatus.BLOCKED,
            queue_priority=4,
            with_report=True,
        )
    )

    response = client.post(
        "/api/v1/b2b/events",
        json=_event("PRODUCT_EDITED", _edited_payload(product_id, queue_priority=2)),
        headers=SERVICE_HEADERS,
    )

    assert response.status_code == 202
    ticket = asyncio.run(_fetch_ticket(db_state.session_factory, product_id))
    assert ticket is not None
    assert ticket.kind == TicketKind.EDIT.value
    assert ticket.status == TicketStatus.PENDING.value
    assert ticket.queue_priority == 2
    assert ticket.moderator_id is None
    assert ticket.date_moderation is None
    assert ticket.moderator_comment is None
    assert ticket.json_before["title"] == "Old phone"
    assert ticket.json_after["title"] == "New phone"
    assert asyncio.run(_count_field_reports(db_state.session_factory)) == 0


def test_edited_updates_in_review(client: TestClient, db_state: DbState) -> None:
    product_id = uuid4()
    asyncio.run(
        _insert_ticket(
            db_state.session_factory,
            product_id=product_id,
            status=TicketStatus.IN_REVIEW,
            queue_priority=3,
            with_report=True,
        )
    )

    response = client.post(
        "/api/v1/b2b/events",
        json=_event("PRODUCT_EDITED", _edited_payload(product_id, queue_priority=3)),
        headers=SERVICE_HEADERS,
    )

    assert response.status_code == 202
    ticket = asyncio.run(_fetch_ticket(db_state.session_factory, product_id))
    assert ticket is not None
    assert ticket.status == TicketStatus.PENDING.value
    assert ticket.kind == TicketKind.EDIT.value
    assert ticket.queue_priority == 3
    assert ticket.moderator_id is None
    assert ticket.claimed_at is None
    assert ticket.claim_expires_at is None
    assert ticket.json_before == {"title": "Old phone", "total_active_quantity": 1}
    assert ticket.json_after == {"title": "New phone", "total_active_quantity": 3}
    assert asyncio.run(_count_field_reports(db_state.session_factory)) == 0


def test_deleted_archived(client: TestClient, db_state: DbState) -> None:
    product_id = uuid4()
    asyncio.run(
        _insert_ticket(
            db_state.session_factory,
            product_id=product_id,
            status=TicketStatus.HARD_BLOCKED,
            with_report=True,
        )
    )

    response = client.post(
        "/api/v1/b2b/events",
        json=_event("PRODUCT_DELETED", {"product_id": str(product_id)}),
        headers=SERVICE_HEADERS,
    )

    assert response.status_code == 202
    assert asyncio.run(_fetch_ticket(db_state.session_factory, product_id)) is None
    assert asyncio.run(_count_field_reports(db_state.session_factory)) == 0
    assert asyncio.run(_count_processed(db_state.session_factory)) == 1


def test_duplicate_event_no_side_effects(client: TestClient, db_state: DbState) -> None:
    product_id = uuid4()
    idempotency_key = uuid4()
    first_event = _event(
        "PRODUCT_CREATED",
        _created_payload(product_id, queue_priority=1, json_after={"title": "First"}),
        idempotency_key=idempotency_key,
    )
    duplicate_event = _event(
        "PRODUCT_CREATED",
        _created_payload(product_id, queue_priority=4, json_after={"title": "Second"}),
        idempotency_key=idempotency_key,
    )

    first_response = client.post("/api/v1/b2b/events", json=first_event, headers=SERVICE_HEADERS)
    duplicate_response = client.post(
        "/api/v1/b2b/events", json=duplicate_event, headers=SERVICE_HEADERS
    )

    assert first_response.status_code == 202
    assert duplicate_response.status_code == 409
    assert duplicate_response.content == b""
    ticket = asyncio.run(_fetch_ticket(db_state.session_factory, product_id))
    assert ticket is not None
    assert ticket.queue_priority == 1
    assert ticket.json_after == {"title": "First"}
    assert asyncio.run(_count_processed(db_state.session_factory)) == 1


def test_missing_service_header_401(client: TestClient, db_state: DbState) -> None:
    response = client.post(
        "/api/v1/b2b/events",
        json=_event("PRODUCT_CREATED", _created_payload(uuid4())),
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert asyncio.run(_count_processed(db_state.session_factory)) == 0


def test_invalid_service_header_401(client: TestClient, db_state: DbState) -> None:
    response = client.post(
        "/api/v1/b2b/events",
        json=_event("PRODUCT_CREATED", _created_payload(uuid4())),
        headers={"X-Service-Key": "wrong-key"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert asyncio.run(_count_processed(db_state.session_factory)) == 0


def test_expired_idempotency_key_can_be_reused(client: TestClient, db_state: DbState) -> None:
    product_id = uuid4()
    idempotency_key = uuid4()
    asyncio.run(
        _insert_processed_event(
            db_state.session_factory,
            idempotency_key=idempotency_key,
            product_id=product_id,
            processed_at=datetime.now(UTC) - timedelta(hours=25),
        )
    )

    response = client.post(
        "/api/v1/b2b/events",
        json=_event(
            "PRODUCT_CREATED",
            _created_payload(product_id, queue_priority=1),
            idempotency_key=idempotency_key,
        ),
        headers=SERVICE_HEADERS,
    )

    assert response.status_code == 202
    ticket = asyncio.run(_fetch_ticket(db_state.session_factory, product_id))
    assert ticket is not None
    assert ticket.status == TicketStatus.PENDING.value
    assert asyncio.run(_count_processed(db_state.session_factory)) == 1
