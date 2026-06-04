"""Tests for POST /api/v1/tickets/{ticket_id}/block (US-MOD-04 soft block).

Behaviour follows moderation/openapi.yaml (the canonical contract):
  * IN_REVIEW -> BLOCKED for a soft reason (HARD_BLOCKED if any reason is hard);
  * a BLOCKED event with hard_block is emitted to B2B;
  * unknown/inactive blocking_reason_id -> 400;
  * a ticket held by another moderator -> 409 (spec lists 409 for «чужой тикет», not 403);
  * field reports use the spec's FieldReport shape {field_path, message, severity};
    an invalid severity -> 400 (the spec has no field_name enum — that is field_path here).
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

PROJECT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_PATH / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH / "src"))

from api.blocking_reasons.domain import BlockingReasonDTO  # noqa: E402
from api.product_moderation import get_b2b_event_client, get_block_repo  # noqa: E402
from api.product_moderation.b2b_client import InMemoryB2BEventClient  # noqa: E402
from api.product_moderation.domain import ModerationCard  # noqa: E402
from api.product_moderation.repository import InMemoryBlockRepository  # noqa: E402
from auth import get_current_moderator_id  # noqa: E402
from main import app  # noqa: E402

MOD_ID = uuid4()
OTHER_MOD_ID = uuid4()


def make_card(*, status: str = "IN_REVIEW", moderator_id: UUID | None = MOD_ID) -> ModerationCard:
    now = datetime.now(UTC)
    return ModerationCard(
        id=uuid4(),
        product_id=uuid4(),
        seller_id=uuid4(),
        category_id=None,
        kind="CREATE",
        status=status,
        queue_priority=1,
        moderator_id=moderator_id,
        claimed_at=now,
        claim_expires_at=now,
        date_created=now,
        date_updated=now,
        date_moderation=None,
        moderator_comment=None,
        json_after={"skus": [{"sku_id": str(uuid4())}]},
    )


def make_reason(*, hard_block: bool, is_active: bool = True, title: str = "Причина") -> Any:
    return BlockingReasonDTO(
        id=uuid4(),
        code="SOME_CODE",
        title=title,
        description=None,
        hard_block=hard_block,
        is_active=is_active,
    )


@pytest.fixture()
def repo() -> InMemoryBlockRepository:
    return InMemoryBlockRepository()


@pytest.fixture()
def events() -> InMemoryB2BEventClient:
    return InMemoryB2BEventClient()


@pytest.fixture()
def client(
    repo: InMemoryBlockRepository, events: InMemoryB2BEventClient
) -> Generator[TestClient]:
    app.dependency_overrides[get_block_repo] = lambda: repo
    app.dependency_overrides[get_b2b_event_client] = lambda: events
    app.dependency_overrides[get_current_moderator_id] = lambda: MOD_ID
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_soft_block_transitions_to_blocked_with_field_reports(
    client: TestClient, repo: InMemoryBlockRepository, events: InMemoryB2BEventClient
) -> None:
    card = make_card()
    reason = make_reason(hard_block=False, title="Фото не соответствует")
    repo.seed_cards(card)
    repo.seed_reasons(reason)

    response = client.post(
        f"/api/v1/tickets/{card.id}/block",
        json={
            "blocking_reason_ids": [str(reason.id)],
            "comment": "Поправьте фото",
            "field_reports": [
                {"field_path": "images[0].url", "message": "Размытое фото", "severity": "ERROR"}
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
    # field reports reached B2B (mapped to its shape).
    assert len(events.blocked_events) == 1
    reports = events.blocked_events[0].field_reports
    assert reports == ({"field_name": "images[0].url", "comment": "Размытое фото", "sku_id": None},)


def test_soft_block_emits_event_to_b2b(
    client: TestClient, repo: InMemoryBlockRepository, events: InMemoryB2BEventClient
) -> None:
    card = make_card()
    reason = make_reason(hard_block=False)
    repo.seed_cards(card)
    repo.seed_reasons(reason)

    response = client.post(
        f"/api/v1/tickets/{card.id}/block",
        json={"blocking_reason_ids": [str(reason.id)]},
    )

    assert response.status_code == 200
    assert len(events.blocked_events) == 1
    event = events.blocked_events[0]
    assert event.hard_block is False
    assert event.product_id == card.product_id
    assert event.blocking_reason_id == reason.id


def test_soft_block_unknown_reason_returns_400(
    client: TestClient, repo: InMemoryBlockRepository
) -> None:
    card = make_card()
    repo.seed_cards(card)  # no reasons seeded → reason id is unknown

    response = client.post(
        f"/api/v1/tickets/{card.id}/block",
        json={"blocking_reason_ids": [str(uuid4())]},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_soft_block_others_card_returns_409(
    client: TestClient, repo: InMemoryBlockRepository
) -> None:
    # Spec lists 409 for «чужой тикет» on /block (no 403); ownership conflict wins.
    card = make_card(moderator_id=OTHER_MOD_ID)
    reason = make_reason(hard_block=False)
    repo.seed_cards(card)
    repo.seed_reasons(reason)

    response = client.post(
        f"/api/v1/tickets/{card.id}/block",
        json={"blocking_reason_ids": [str(reason.id)]},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "TICKET_NOT_ASSIGNED"


def test_soft_block_invalid_field_report_returns_400(
    client: TestClient, repo: InMemoryBlockRepository
) -> None:
    # The spec's FieldReport has no field_name enum; severity is the constrained enum.
    card = make_card()
    reason = make_reason(hard_block=False)
    repo.seed_cards(card)
    repo.seed_reasons(reason)

    response = client.post(
        f"/api/v1/tickets/{card.id}/block",
        json={
            "blocking_reason_ids": [str(reason.id)],
            "field_reports": [
                {"field_path": "title", "message": "плохо", "severity": "CRITICAL"}
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_hard_only_reason_routes_to_hard(
    client: TestClient, repo: InMemoryBlockRepository, events: InMemoryB2BEventClient
) -> None:
    # hard_block=true reason on the shared /block endpoint → HARD_BLOCKED + hard event.
    card = make_card()
    reason = make_reason(hard_block=True, title="Запрещённый товар")
    repo.seed_cards(card)
    repo.seed_reasons(reason)

    response = client.post(
        f"/api/v1/tickets/{card.id}/block",
        json={"blocking_reason_ids": [str(reason.id)]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "HARD_BLOCKED"
    assert events.blocked_events[0].hard_block is True
