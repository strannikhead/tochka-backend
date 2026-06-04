from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

PROJECT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_PATH / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH / "src"))

from auth import get_current_moderator_id  # noqa: E402
from main import app  # noqa: E402
from modqueue.repository import InMemoryQueueRepository  # noqa: E402
from modqueue.router import get_queue_repo  # noqa: E402

MOD_1_ID: UUID
MOD_2_ID: UUID


@pytest.fixture()
def queue_repo() -> InMemoryQueueRepository:
    return InMemoryQueueRepository()


@pytest.fixture()
def moderator_id(request: pytest.FixtureRequest) -> UUID:
    from uuid import uuid4

    return getattr(request, "param", uuid4())


@pytest.fixture()
def client(queue_repo: InMemoryQueueRepository, moderator_id: UUID) -> Generator[TestClient]:
    app.dependency_overrides[get_queue_repo] = lambda: queue_repo
    app.dependency_overrides[get_current_moderator_id] = lambda: moderator_id
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
