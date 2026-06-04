"""Tests for POST /api/v1/queue/claim."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

PROJECT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_PATH / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH / "src"))

from auth import get_current_moderator_id  # noqa: E402
from main import app  # noqa: E402
from modqueue.domain import Ticket  # noqa: E402
from modqueue.repository import InMemoryQueueRepository  # noqa: E402
from modqueue.router import get_queue_repo  # noqa: E402

# ---- helpers ----

MOD_1 = uuid4()
MOD_2 = uuid4()


def make_pending_ticket(
    *,
    queue_priority: int = 1,
    updated_at: datetime | None = None,
) -> Ticket:
    now = updated_at or datetime.now(UTC)
    return Ticket(
        id=uuid4(),
        product_id=uuid4(),
        seller_id=uuid4(),
        category_id=None,
        kind="CREATE",
        status="PENDING",
        queue_priority=queue_priority,
        assigned_moderator_id=None,
        claimed_at=None,
        claim_expires_at=None,
        decision_at=None,
        created_at=now,
        updated_at=now,
    )


def make_client(moderator_id: UUID, queue_repo: InMemoryQueueRepository) -> TestClient:
    app.dependency_overrides[get_queue_repo] = lambda: queue_repo
    app.dependency_overrides[get_current_moderator_id] = lambda: moderator_id
    return TestClient(app)


# ---- tests ----


def test_next_returns_oldest_pending(
    client: TestClient, queue_repo: InMemoryQueueRepository, moderator_id: UUID
) -> None:
    """PENDING → IN_REVIEW: oldest ticket (by date_updated) is returned and assigned."""
    older = make_pending_ticket(updated_at=datetime.now(UTC) - timedelta(hours=1))
    newer = make_pending_ticket()
    queue_repo.seed(newer, older)  # reverse order to catch sorting bugs

    r = client.post("/api/v1/queue/claim")

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(older.id)
    assert body["status"] == "IN_REVIEW"
    assert body["assigned_moderator_id"] == str(moderator_id)
    assert body["claimed_at"] is not None
    assert body["claim_expires_at"] is not None


def test_concurrent_two_moderators_get_different_cards(
    queue_repo: InMemoryQueueRepository,
) -> None:
    """Two moderators claiming in sequence receive different tickets."""
    t1 = make_pending_ticket()
    t2 = make_pending_ticket()
    queue_repo.seed(t1, t2)

    with make_client(MOD_1, queue_repo) as c1:
        r1 = c1.post("/api/v1/queue/claim")
    with make_client(MOD_2, queue_repo) as c2:
        r2 = c2.post("/api/v1/queue/claim")
    app.dependency_overrides.clear()

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["id"] != r2.json()["id"]


def test_empty_queue_returns_204(client: TestClient, queue_repo: InMemoryQueueRepository) -> None:
    """Returns 204 when no PENDING tickets exist."""
    r = client.post("/api/v1/queue/claim")
    assert r.status_code == 204


def test_moderator_already_has_in_review_returns_409(
    client: TestClient, queue_repo: InMemoryQueueRepository
) -> None:
    """Moderator cannot claim a second ticket while holding an active IN_REVIEW one."""
    queue_repo.seed(make_pending_ticket(), make_pending_ticket())

    assert client.post("/api/v1/queue/claim").status_code == 200
    r = client.post("/api/v1/queue/claim")
    assert r.status_code == 409
    assert r.json()["code"] == "MODERATOR_ALREADY_IN_REVIEW"


# ---- async concurrency test (directly on repo) ----


async def test_concurrent_claims_via_asyncio_gather() -> None:
    """asyncio.gather: two concurrent claims on InMemory repo yield distinct tickets."""
    repo = InMemoryQueueRepository()
    repo.seed(
        make_pending_ticket(updated_at=datetime.now(UTC) - timedelta(seconds=10)),
        make_pending_ticket(),
    )

    result_a, result_b = await asyncio.gather(
        repo.claim_next(uuid4(), None, None, 30),
        repo.claim_next(uuid4(), None, None, 30),
    )

    assert result_a is not None
    assert result_b is not None
    assert result_a.id != result_b.id


def test_auto_priority_selects_highest_first(
    client: TestClient, queue_repo: InMemoryQueueRepository
) -> None:
    """Without queue_priority, auto-prioritisation picks priority 1 before 4."""
    queue_repo.seed(make_pending_ticket(queue_priority=4), make_pending_ticket(queue_priority=1))

    r = client.post("/api/v1/queue/claim")

    assert r.status_code == 200
    assert r.json()["queue_priority"] == 1


def test_missing_auth_returns_401(queue_repo: InMemoryQueueRepository) -> None:
    """Request without Authorization header returns 401, not 422."""
    app.dependency_overrides[get_queue_repo] = lambda: queue_repo
    app.dependency_overrides.pop(get_current_moderator_id, None)
    with TestClient(app) as c:
        r = c.post("/api/v1/queue/claim")
    app.dependency_overrides.clear()

    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"
