from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


class ModerationClient:
    def __init__(self, base_url: str, service_key: str) -> None:
        self._base_url = base_url
        self._service_key = service_key

    async def send_created_event(
        self,
        *,
        idempotency_key: UUID,
        product_id: UUID,
        seller_id: UUID,
        date: datetime,
    ) -> None:
        payload = {
            "type": "CREATED",
            "idempotency_key": str(idempotency_key),
            "product_id": str(product_id),
            "seller_id": str(seller_id),
            "date": date.isoformat(),
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/events/product",
                    json=payload,
                    headers={"X-Service-Key": self._service_key},
                    timeout=5.0,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            # Fire-and-forget: log the failure but don't roll back the transaction.
            logger.error(
                "Failed to send CREATED event to moderation for product %s: %s",
                product_id,
                exc,
            )
