from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

import httpx

# Stable namespace so the same approval always maps to the same idempotency key,
# letting B2B dedup retries and never double-publish a product to the catalog.
_EVENT_NAMESPACE = uuid.UUID("6f8d3c2e-1a4b-4c6d-9e0f-2b3c4d5e6f70")


def moderated_idempotency_key(product_id: UUID) -> UUID:
    return uuid.uuid5(_EVENT_NAMESPACE, f"{product_id}:MODERATED")


def blocked_idempotency_key(product_id: UUID, hard_block: bool) -> UUID:
    kind = "HARD_BLOCKED" if hard_block else "BLOCKED"
    return uuid.uuid5(_EVENT_NAMESPACE, f"{product_id}:{kind}")


@dataclass(frozen=True)
class ModeratedEvent:
    product_id: UUID
    status: str
    idempotency_key: UUID


@dataclass(frozen=True)
class BlockedEvent:
    product_id: UUID
    hard_block: bool
    blocking_reason_id: UUID
    blocking_reason_title: str
    moderator_comment: str | None
    field_reports: tuple[dict[str, object], ...]
    idempotency_key: UUID


class B2BEventClientProtocol(Protocol):
    async def emit_moderated(self, product_id: UUID) -> None:
        """Notify B2B that the product passed moderation (status MODERATED)."""
        ...

    async def emit_blocked(
        self,
        *,
        product_id: UUID,
        hard_block: bool,
        blocking_reason_id: UUID,
        blocking_reason_title: str,
        moderator_comment: str | None,
        field_reports: list[dict[str, object]],
    ) -> None:
        """Notify B2B that the product was blocked (BLOCKED / HARD_BLOCKED)."""
        ...


class B2BEventError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class InMemoryB2BEventClient:
    """Records emitted events for assertions in tests."""

    def __init__(self) -> None:
        self.events: list[ModeratedEvent] = []
        self.blocked_events: list[BlockedEvent] = []

    async def emit_moderated(self, product_id: UUID) -> None:
        self.events.append(
            ModeratedEvent(
                product_id=product_id,
                status="MODERATED",
                idempotency_key=moderated_idempotency_key(product_id),
            )
        )

    async def emit_blocked(
        self,
        *,
        product_id: UUID,
        hard_block: bool,
        blocking_reason_id: UUID,
        blocking_reason_title: str,
        moderator_comment: str | None,
        field_reports: list[dict[str, object]],
    ) -> None:
        self.blocked_events.append(
            BlockedEvent(
                product_id=product_id,
                hard_block=hard_block,
                blocking_reason_id=blocking_reason_id,
                blocking_reason_title=blocking_reason_title,
                moderator_comment=moderator_comment,
                field_reports=tuple(field_reports),
                idempotency_key=blocked_idempotency_key(product_id, hard_block),
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

    async def emit_blocked(
        self,
        *,
        product_id: UUID,
        hard_block: bool,
        blocking_reason_id: UUID,
        blocking_reason_title: str,
        moderator_comment: str | None,
        field_reports: list[dict[str, object]],
    ) -> None:
        url = f"{self._base_url}/api/v1/moderation/events"
        headers = {"X-Service-Key": self._service_key} if self._service_key else {}
        # Shape matches B2B ModerationEventRequest (US-B2B-09).
        payload = {
            "idempotency_key": str(blocked_idempotency_key(product_id, hard_block)),
            "product_id": str(product_id),
            "event_type": "BLOCKED",
            "hard_block": hard_block,
            "blocking_reason_id": str(blocking_reason_id),
            "blocking_reason_title": blocking_reason_title,
            "moderator_comment": moderator_comment,
            "field_reports": field_reports,
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise B2BEventError("Unable to reach B2B", None) from exc
        if response.status_code not in (200, 202, 204, 409):
            raise B2BEventError(
                f"Unexpected B2B response: {response.status_code}", response.status_code
            )
