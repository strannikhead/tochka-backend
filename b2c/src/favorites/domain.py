from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class FavoriteEntry:
    user_id: UUID
    product_id: UUID
    added_at: datetime


@dataclass(frozen=True)
class ProductSubscriptionEntry:
    id: UUID
    user_id: UUID
    product_id: UUID
    events: list[str]
    created_at: datetime
