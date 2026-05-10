from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class NotifyOn(StrEnum):
    IN_STOCK = "IN_STOCK"
    PRICE_DOWN = "PRICE_DOWN"


class SubscribeRequest(BaseModel):
    notify_on: list[str] | None = None


class SubscriptionResponse(BaseModel):
    id: UUID
    product: dict[str, Any]
    notify_on: list[NotifyOn]
    created_at: datetime
