from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


class TicketNotFoundError(Exception):
    """Raised when no ticket exists for the id. -> 404"""


class TicketWrongStatusError(Exception):
    """Raised when the ticket is not IN_REVIEW (edited, already decided, hard-blocked). -> 409"""


class TicketNotAssignedError(Exception):
    """Raised when the ticket is held by a different moderator. -> 409"""


class TicketWithoutSkuError(Exception):
    """Raised when the product has no SKU and cannot be approved. -> 409"""


@dataclass(frozen=True)
class ModerationCard:
    """In-memory view of a product_moderation row, carrying the full ticket shape."""

    id: UUID
    product_id: UUID
    seller_id: UUID
    category_id: UUID | None
    kind: str
    status: str
    queue_priority: int
    moderator_id: UUID | None
    claimed_at: datetime | None
    claim_expires_at: datetime | None
    date_created: datetime
    date_updated: datetime
    date_moderation: datetime | None
    moderator_comment: str | None
    json_after: dict[str, Any]


def has_sku(json_after: dict[str, Any]) -> bool:
    """A product is approvable only if its snapshot carries at least one SKU."""
    skus = json_after.get("skus")
    return bool(skus)
