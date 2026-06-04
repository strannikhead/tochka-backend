"""US-MOD-06: blocking-reasons reference dictionary.

Behaviour follows moderation/openapi.yaml (GET /api/v1/blocking-reasons):
  * list returns active reasons with id, code, title, hard_block, is_active;
  * is_active filter defaults to true → deactivated reasons are hidden;
  * hard_block filter narrows soft vs hard reasons;
  * DELETE is a soft deactivation (rows are never physically removed, so historical
    BLOCKED cards keep their FK reference).
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from api.blocking_reasons import get_reasons_repo
from api.blocking_reasons.domain import BlockingReasonDTO
from api.blocking_reasons.repository import InMemoryBlockingReasonsRepository
from auth import get_current_moderator_id
from main import app

MODERATOR_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


def _reason(
    *, code: str, title: str, hard_block: bool, is_active: bool = True
) -> BlockingReasonDTO:
    return BlockingReasonDTO(
        id=uuid4(),
        code=code,
        title=title,
        description=None,
        hard_block=hard_block,
        is_active=is_active,
    )


@pytest.fixture()
def repo() -> InMemoryBlockingReasonsRepository:
    return InMemoryBlockingReasonsRepository()


@pytest.fixture()
def client(repo: InMemoryBlockingReasonsRepository) -> Generator[TestClient]:
    app.dependency_overrides[get_reasons_repo] = lambda: repo
    app.dependency_overrides[get_current_moderator_id] = lambda: MODERATOR_ID
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_list_returns_active_reasons(
    client: TestClient, repo: InMemoryBlockingReasonsRepository
) -> None:
    repo.seed(
        _reason(code="FORBIDDEN_GOODS", title="Запрещённый товар", hard_block=True),
        _reason(code="BAD_PHOTO", title="Фото не соответствует", hard_block=False),
    )

    response = client.get("/api/v1/blocking-reasons")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    for item in items:
        assert item.keys() >= {"id", "code", "title", "hard_block", "is_active"}
        assert item["is_active"] is True
    titles = {item["title"] for item in items}
    assert titles == {"Запрещённый товар", "Фото не соответствует"}


def test_inactive_reasons_not_visible(
    client: TestClient, repo: InMemoryBlockingReasonsRepository
) -> None:
    repo.seed(
        _reason(code="ACTIVE_ONE", title="Активная", hard_block=False),
        _reason(code="OLD_ONE", title="Деактивированная", hard_block=False, is_active=False),
    )

    response = client.get("/api/v1/blocking-reasons")

    assert response.status_code == 200
    codes = {item["code"] for item in response.json()}
    assert codes == {"ACTIVE_ONE"}
    assert "OLD_ONE" not in codes


def test_list_filters_by_hard_block(
    client: TestClient, repo: InMemoryBlockingReasonsRepository
) -> None:
    repo.seed(
        _reason(code="HARD_ONE", title="Жёсткая", hard_block=True),
        _reason(code="SOFT_ONE", title="Мягкая", hard_block=False),
    )

    hard = client.get("/api/v1/blocking-reasons", params={"hard_block": "true"}).json()
    soft = client.get("/api/v1/blocking-reasons", params={"hard_block": "false"}).json()

    assert [r["code"] for r in hard] == ["HARD_ONE"]
    assert [r["code"] for r in soft] == ["SOFT_ONE"]


def test_referenced_reason_cannot_be_deleted(
    client: TestClient, repo: InMemoryBlockingReasonsRepository
) -> None:
    # A reason referenced by historical BLOCKED cards must not be physically removed.
    reason = _reason(code="FORBIDDEN_GOODS", title="Запрещёнка", hard_block=True)
    repo.seed(reason)

    response = client.delete(f"/api/v1/blocking-reasons/{reason.id}")

    assert response.status_code == 204
    # Not in the default (active) list...
    active = client.get("/api/v1/blocking-reasons").json()
    assert all(r["id"] != str(reason.id) for r in active)
    # ...but still present (deactivated), i.e. not physically deleted → FK preserved.
    inactive = client.get("/api/v1/blocking-reasons", params={"is_active": "false"}).json()
    match = [r for r in inactive if r["id"] == str(reason.id)]
    assert len(match) == 1
    assert match[0]["is_active"] is False


def test_create_duplicate_code_returns_409(
    client: TestClient, repo: InMemoryBlockingReasonsRepository
) -> None:
    repo.seed(_reason(code="FORBIDDEN_GOODS", title="Запрещёнка", hard_block=True))

    response = client.post(
        "/api/v1/blocking-reasons",
        json={"code": "FORBIDDEN_GOODS", "title": "Дубль", "hard_block": True},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"
