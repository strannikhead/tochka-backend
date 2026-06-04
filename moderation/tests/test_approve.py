"""Tests for POST /api/v1/tickets/{ticket_id}/approve (US-MOD-03).

Behaviour follows moderation/openapi.yaml (the canonical contract):
ticket status transitions IN_REVIEW -> APPROVED, a MODERATED event is emitted
to B2B, and a ticket held by another moderator yields 409 (not 403).
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

from api.product_moderation import (  # noqa: E402
    get_approve_repo,
    get_b2b_event_client,
)
from api.product_moderation.b2b_client import InMemoryB2BEventClient  # noqa: E402
from api.product_moderation.domain import ModerationCard  # noqa: E402
from api.product_moderation.repository import InMemoryApproveRepository  # noqa: E402
from auth import get_current_moderator_id  # noqa: E402
from main import app  # noqa: E402

MOD_ID = uuid4()
OTHER_MOD_ID = uuid4()


def make_card(
    *,
    status: str = "IN_REVIEW",
    moderator_id: UUID | None = MOD_ID,
    json_after: dict[str, Any] | None = None,
) -> ModerationCard:
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
        json_after=json_after if json_after is not None else {"skus": [{"sku_id": str(uuid4())}]},
    )


@pytest.fixture()
def repo() -> InMemoryApproveRepository:
    return InMemoryApproveRepository()


@pytest.fixture()
def events() -> InMemoryB2BEventClient:
    return InMemoryB2BEventClient()


@pytest.fixture()
def client(
    repo: InMemoryApproveRepository, events: InMemoryB2BEventClient
) -> Generator[TestClient]:
    app.dependency_overrides[get_approve_repo] = lambda: repo
    app.dependency_overrides[get_b2b_event_client] = lambda: events
    app.dependency_overrides[get_current_moderator_id] = lambda: MOD_ID
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_approve_transitions_to_moderated_and_emits_event(
    client: TestClient, repo: InMemoryApproveRepository, events: InMemoryB2BEventClient
) -> None:
    """Happy path: ticket IN_REVIEW -> APPROVED and exactly one MODERATED event reaches B2B."""
    card = make_card()
    repo.seed(card)

    r = client.post(f"/api/v1/tickets/{card.id}/approve")

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(card.id)
    assert body["product_id"] == str(card.product_id)
    assert body["status"] == "APPROVED"

    assert repo.get(card.id).status == "APPROVED"  # type: ignore[union-attr]
    assert len(events.events) == 1
    assert events.events[0].product_id == card.product_id
    assert events.events[0].status == "MODERATED"


def test_approve_others_card_returns_409(
    client: TestClient, repo: InMemoryApproveRepository, events: InMemoryB2BEventClient
) -> None:
    """A moderator cannot approve a ticket held by someone else (OpenAPI: 409)."""
    card = make_card(moderator_id=OTHER_MOD_ID)
    repo.seed(card)

    r = client.post(f"/api/v1/tickets/{card.id}/approve")

    assert r.status_code == 409
    assert r.json()["code"] == "TICKET_NOT_ASSIGNED"
    assert repo.get(card.id).status == "IN_REVIEW"  # type: ignore[union-attr]
    assert events.events == []


def test_approve_after_edited_returns_409(
    client: TestClient, repo: InMemoryApproveRepository, events: InMemoryB2BEventClient
) -> None:
    """Seller edited during review -> ticket re-queued to PENDING -> approve is 409."""
    card = make_card(status="PENDING")
    repo.seed(card)

    r = client.post(f"/api/v1/tickets/{card.id}/approve")

    assert r.status_code == 409
    assert r.json()["code"] == "TICKET_WRONG_STATUS"
    assert events.events == []


def test_approve_without_sku_returns_409(
    client: TestClient, repo: InMemoryApproveRepository, events: InMemoryB2BEventClient
) -> None:
    """A product without any SKU cannot be approved."""
    card = make_card(json_after={"skus": []})
    repo.seed(card)

    r = client.post(f"/api/v1/tickets/{card.id}/approve")

    assert r.status_code == 409
    assert r.json()["code"] == "TICKET_WITHOUT_SKU"
    assert events.events == []


def test_approve_unknown_ticket_returns_404(
    client: TestClient, events: InMemoryB2BEventClient
) -> None:
    """No ticket for the id -> 404."""
    r = client.post(f"/api/v1/tickets/{uuid4()}/approve")

    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"
    assert events.events == []


def test_second_approve_does_not_double_emit(
    client: TestClient, repo: InMemoryApproveRepository, events: InMemoryB2BEventClient
) -> None:
    """Idempotency: re-approving an already-APPROVED ticket is 409 and emits nothing new."""
    card = make_card()
    repo.seed(card)

    first = client.post(f"/api/v1/tickets/{card.id}/approve")
    second = client.post(f"/api/v1/tickets/{card.id}/approve")

    assert first.status_code == 200
    assert second.status_code == 409
    assert len(events.events) == 1
