from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Banner:
    id: UUID
    title: str | None
    image_url: str
    link: str
    ordering: int
    active_from: datetime | None = None
    active_to: datetime | None = None
    is_active: bool = True
