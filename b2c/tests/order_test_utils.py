from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx
from b2b.src.main import app as b2b_app
from src.orders.domain import CatalogSkuSnapshot, ReserveFailedItem, ReserveResult


@dataclass
class LiveCheckoutCatalogClient:
    async def get_skus_by_ids(self, sku_ids):
        transport = httpx.ASGITransport(app=b2b_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://b2b") as client:
            response = await client.get(
                "/api/v1/products",
                params={"ids": ",".join(str(sku_id) for sku_id in sku_ids)},
                headers={"X-Service-Key": "dev-service-key"},
            )

        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", []) if isinstance(payload, dict) else []
        skus: list[CatalogSkuSnapshot] = []
        for product in items:
            for sku in product.get("skus", []):
                skus.append(
                    CatalogSkuSnapshot(
                        sku_id=UUID(str(sku["id"])),
                        product_id=UUID(str(sku["product_id"])),
                        product_title=str(product["title"]),
                        sku_name=str(sku["name"]),
                        unit_price=int(sku["price"]),
                        active_quantity=int(sku["active_quantity"]),
                        product_status=str(product.get("status", "MODERATED")),
                        product_deleted=bool(product.get("deleted", False)),
                    )
                )
        wanted = {UUID(str(sku_id)) for sku_id in sku_ids}
        return [sku for sku in skus if sku.sku_id in wanted]

    async def reserve(self, *, idempotency_key, items):
        transport = httpx.ASGITransport(app=b2b_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://b2b") as client:
            response = await client.post(
                "/api/v1/inventory/reserve",
                json={
                    "idempotency_key": str(idempotency_key),
                    "order_id": str(idempotency_key),
                    "items": [
                        {"sku_id": str(item.sku_id), "quantity": item.quantity} for item in items
                    ],
                },
                headers={"X-Service-Key": "dev-service-key"},
            )

        payload = response.json()
        if response.status_code == 200:
            return ReserveResult(reserved=True)
        if response.status_code == 409:
            return ReserveResult(
                reserved=False,
                failed_items=tuple(
                    ReserveFailedItem(
                        sku_id=UUID(str(item["sku_id"])),
                        requested=int(item.get("requested", 0)),
                        available=int(item.get("available", 0)),
                        reason=str(item.get("reason", "INSUFFICIENT_STOCK")),
                    )
                    for item in payload.get("failed_items", [])
                ),
            )
        response.raise_for_status()


def build_sku(
    *,
    sku_id: UUID,
    product_id: UUID,
    product_title: str,
    sku_name: str,
    unit_price: int,
    active_quantity: int,
    product_status: str = "MODERATED",
    product_deleted: bool = False,
) -> CatalogSkuSnapshot:
    return CatalogSkuSnapshot(
        sku_id=sku_id,
        product_id=product_id,
        product_title=product_title,
        sku_name=sku_name,
        unit_price=unit_price,
        active_quantity=active_quantity,
        product_status=product_status,
        product_deleted=product_deleted,
    )


def auth_header(token: str | UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
