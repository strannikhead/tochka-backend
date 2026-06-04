from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class ModeratorAlreadyInReviewError(Exception):
    """Raised when a moderator already holds an active IN_REVIEW ticket."""


@dataclass(frozen=True)
class Ticket:
    id: UUID
    product_id: UUID
    seller_id: UUID
    category_id: UUID | None
    kind: str  # "CREATE" | "EDIT"
    status: str  # "PENDING" | "IN_REVIEW" | ...
    queue_priority: int
    assigned_moderator_id: UUID | None
    claimed_at: datetime | None
    claim_expires_at: datetime | None
    decision_at: datetime | None
    created_at: datetime
    updated_at: datetime | None
