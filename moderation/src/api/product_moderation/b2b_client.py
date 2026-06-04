from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import httpx

# Stable namespace so the same approval always maps to the same idempotency key,
# letting B2B dedup retries and never double-publish a product to the catalog.
_EVENT_NAMESPACE = uuid.UUID("6f8d3c2e-1a4b-4c6d-9e0f-2b3c4d5e6f70")


def moderated_idempotency_key(product_id: UUID) -> UUID:
    return uuid.uuid5(_EVENT_NAMESPACE, f"{product_id}:MODERATED")


@dataclass(frozen=True)
class ModeratedEvent:
    product_id: UUID
    status: str
    idempotency_key: UUID


class B2BEventClientProtocol(Protocol):
    async def emit_moderated(self, product_id: UUID) -> None:
        """Notify B2B that the product passed moderation (status MODERATED)."""
        ...


class B2BEventError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class InMemoryB2BEventClient:
    """Records emitted events for assertions in tests."""

    def __init__(self) -> None:
        self.events: list[ModeratedEvent] = []

    async def emit_moderated(self, product_id: UUID) -> None:
        self.events.append(
            ModeratedEvent(
                product_id=product_id,
                status="MODERATED",
                idempotency_key=moderated_idempotency_key(product_id),
            )
        )


class HttpB2BEventClient:
    """Synchronously POSTs the MODERATED event to the B2B service."""

    def __init__(self, base_url: str | None = None, timeout: float = 5.0) -> None:
        self._base_url = (base_url or os.getenv("B2B_BASE_URL") or "http://localhost:8001").rstrip(
            "/"
        )
        self._timeout = timeout
        self._service_key = os.getenv("B2B_SERVICE_KEY")

    async def emit_moderated(self, product_id: UUID) -> None:
        url = f"{self._base_url}/api/v1/moderation/events"
        headers = {"X-Service-Key": self._service_key} if self._service_key else {}
        payload = {
            "product_id": str(product_id),
            "status": "MODERATED",
            "idempotency_key": str(moderated_idempotency_key(product_id)),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise B2BEventError("Unable to reach B2B", None) from exc
        # 409 means B2B already processed this idempotency key — treat as success.
        if response.status_code not in (200, 202, 409):
            raise B2BEventError(
                f"Unexpected B2B response: {response.status_code}", response.status_code
            )
