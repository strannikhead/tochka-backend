from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx

logger = logging.getLogger(__name__)


class B2cClient:
    def __init__(self, base_url: str, service_key: str) -> None:
        self._base_url = base_url
        self._service_key = service_key

    async def send_sku_out_of_stock(
        self,
        *,
        sku_id: UUID,
        product_id: UUID,
        available_quantity: int,
    ) -> None:
        payload = {
            "event_type": "SKU_OUT_OF_STOCK",
            "idempotency_key": str(uuid4()),
            "occurred_at": datetime.now(UTC).isoformat(),
            "payload": {
                "sku_id": str(sku_id),
                "product_id": str(product_id),
                "available_quantity": available_quantity,
            },
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/b2b/events",
                    json=payload,
                    headers={"X-Service-Key": self._service_key},
                    timeout=5.0,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "Failed to send SKU_OUT_OF_STOCK event to B2C for sku %s: %s",
                sku_id,
                exc,
            )
