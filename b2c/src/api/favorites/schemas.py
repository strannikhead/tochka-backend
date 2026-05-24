from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SubscriptionEvent(StrEnum):
    BACK_IN_STOCK = "BACK_IN_STOCK"
    PRICE_DROP = "PRICE_DROP"


DEFAULT_SUBSCRIPTION_EVENTS = [
    SubscriptionEvent.BACK_IN_STOCK,
    SubscriptionEvent.PRICE_DROP,
]


class SubscribeRequest(BaseModel):
    events: list[SubscriptionEvent] = Field(
        default_factory=lambda: DEFAULT_SUBSCRIPTION_EVENTS.copy(),
    )
