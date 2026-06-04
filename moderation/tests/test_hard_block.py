"""Tests for US-MOD-05 hard block (terminal HARD_BLOCKED status).

Behaviour follows moderation/openapi.yaml + canon:
  * a hard_block=true reason on POST /tickets/{id}/block → HARD_BLOCKED + event with
    hard_block=true to B2B;
  * HARD_BLOCKED is terminal — any mutating endpoint (approve, block) returns 403.

EDITED-ignored / DELETED-removes are inbound-event behaviours, covered by the
b2b_events DB tests (test_b2b_events.py).
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

PROJECT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_PATH / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH / "src"))

from api.blocking_reasons.domain import BlockingReasonDTO  # noqa: E402
from api.product_moderation import (  # noqa: E402
    get_approve_repo,
    get_b2b_event_client,
    get_block_repo,
)
from api.product_moderation.b2b_client import InMemoryB2BEventClient  # noqa: E402
from api.product_moderation.domain import ModerationCard  # noqa: E402
from api.product_moderation.repository import (  # noqa: E402
    InMemoryApproveRepository,
    InMemoryBlockRepository,
)
from auth import get_current_moderator_id  # noqa: E402
from main import app  # noqa: E402

MOD_ID = uuid4()


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


def hard_reason() -> BlockingReasonDTO:
    return BlockingReasonDTO(
        id=uuid4(),
        code="FORBIDDEN_GOODS",
        title="Запрещённый товар",
        description=None,
        hard_block=True,
        is_active=True,
    )


@pytest.fixture()
def block_repo() -> InMemoryBlockRepository:
    return InMemoryBlockRepository()


@pytest.fixture()
def approve_repo() -> InMemoryApproveRepository:
    return InMemoryApproveRepository()


@pytest.fixture()
def events() -> InMemoryB2BEventClient:
    return InMemoryB2BEventClient()


@pytest.fixture()
def client(
    block_repo: InMemoryBlockRepository,
    approve_repo: InMemoryApproveRepository,
    events: InMemoryB2BEventClient,
) -> Generator[TestClient]:
    app.dependency_overrides[get_block_repo] = lambda: block_repo
    app.dependency_overrides[get_approve_repo] = lambda: approve_repo
    app.dependency_overrides[get_b2b_event_client] = lambda: events
    app.dependency_overrides[get_current_moderator_id] = lambda: MOD_ID
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_hard_block_transitions_to_terminal_and_emits_event(
    client: TestClient, block_repo: InMemoryBlockRepository, events: InMemoryB2BEventClient
) -> None:
    card = make_card()
    reason = hard_reason()
    block_repo.seed_cards(card)
    block_repo.seed_reasons(reason)

    response = client.post(
        f"/api/v1/tickets/{card.id}/block",
        json={"blocking_reason_ids": [str(reason.id)]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "HARD_BLOCKED"
    assert len(events.blocked_events) == 1


def test_hard_block_event_carries_hard_block_true(
    client: TestClient, block_repo: InMemoryBlockRepository, events: InMemoryB2BEventClient
) -> None:
    card = make_card()
    reason = hard_reason()
    block_repo.seed_cards(card)
    block_repo.seed_reasons(reason)

    client.post(f"/api/v1/tickets/{card.id}/block", json={"blocking_reason_ids": [str(reason.id)]})

    assert events.blocked_events[0].hard_block is True


def test_any_modify_on_hard_blocked_returns_403(
    client: TestClient,
    block_repo: InMemoryBlockRepository,
    approve_repo: InMemoryApproveRepository,
) -> None:
    # A terminal HARD_BLOCKED ticket rejects every mutating endpoint with 403.
    card = make_card(status="HARD_BLOCKED")
    approve_repo.seed(card)
    block_repo.seed_cards(card)
    block_repo.seed_reasons(hard_reason())

    approve_response = client.post(f"/api/v1/tickets/{card.id}/approve")
    block_response = client.post(
        f"/api/v1/tickets/{card.id}/block",
        json={"blocking_reason_ids": [str(uuid4())]},
    )

    assert approve_response.status_code == 403
    assert approve_response.json()["code"] == "FORBIDDEN"
    assert block_response.status_code == 403
    assert block_response.json()["code"] == "FORBIDDEN"
