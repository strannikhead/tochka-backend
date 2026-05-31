from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any, Protocol
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.orders.db_models import Order as OrderRow
from src.orders.db_models import OrderItem as OrderItemRow
from src.orders.db_models import OrderStatus as DbOrderStatus
from src.orders.domain import (
    CatalogSkuSnapshot,
    OrderItemSnapshot,
    OrderSnapshot,
    ReserveFailedItem,
    ReserveRequestItem,
    ReserveResult,
)
from src.orders.domain import (
    OrderStatus as DomainOrderStatus,
)


class OrdersRepository(Protocol):
    async def get_by_idempotency_key(self, idempotency_key: UUID) -> OrderSnapshot | None: ...

    async def get_for_user(self, *, order_id: UUID, user_id: UUID) -> OrderSnapshot | None: ...

    async def get_by_id(self, order_id: UUID) -> OrderSnapshot | None: ...

    async def list_by_status(
        self,
        *,
        status: str,
        limit: int,
        offset: int = 0,
    ) -> list[OrderSnapshot]: ...

    async def update_status_for_user(
        self,
        *,
        order_id: UUID,
        user_id: UUID,
        status: str,
    ) -> OrderSnapshot | None: ...

    async def update_status(self, *, order_id: UUID, status: str) -> OrderSnapshot | None: ...

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
        status: str | None = None,
    ) -> tuple[list[OrderSnapshot], int]: ...

    async def save(self, order: OrderSnapshot) -> OrderSnapshot: ...


class CheckoutCatalogClient(Protocol):
    async def get_skus_by_ids(self, sku_ids: Iterable[UUID]) -> list[CatalogSkuSnapshot]: ...

    async def reserve(
        self,
        *,
        order_id: UUID,
        idempotency_key: UUID,
        items: list[ReserveRequestItem],
    ) -> ReserveResult: ...

    async def unreserve(
        self,
        *,
        order_id: UUID,
        items: list[ReserveRequestItem],
    ) -> None: ...

    async def fulfill(
        self,
        *,
        order_id: UUID,
        items: list[ReserveRequestItem],
    ) -> None: ...


class UpstreamServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SqlAlchemyOrdersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_idempotency_key(self, idempotency_key: UUID) -> OrderSnapshot | None:
        stmt = (
            select(OrderRow)
            .options(selectinload(OrderRow.items))
            .where(OrderRow.idempotency_key == idempotency_key)
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return _order_row_to_snapshot(row)

    async def get_for_user(self, *, order_id: UUID, user_id: UUID) -> OrderSnapshot | None:
        stmt = (
            select(OrderRow)
            .options(selectinload(OrderRow.items))
            .where(OrderRow.id == order_id, OrderRow.user_id == user_id)
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return _order_row_to_snapshot(row)

    async def get_by_id(self, order_id: UUID) -> OrderSnapshot | None:
        row = await self._load_row(order_id=order_id)
        if row is None:
            return None
        return _order_row_to_snapshot(row)

    async def list_by_status(
        self,
        *,
        status: str,
        limit: int,
        offset: int = 0,
    ) -> list[OrderSnapshot]:
        try:
            db_status = DbOrderStatus(status)
        except ValueError:
            return []

        stmt = (
            select(OrderRow)
            .options(selectinload(OrderRow.items))
            .where(OrderRow.status == db_status)
            .order_by(OrderRow.created_at.asc(), OrderRow.id.asc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_order_row_to_snapshot(row) for row in rows]

    async def update_status_for_user(
        self,
        *,
        order_id: UUID,
        user_id: UUID,
        status: str,
    ) -> OrderSnapshot | None:
        row = await self._load_row(order_id=order_id, user_id=user_id)
        if row is None:
            return None
        row.status = DbOrderStatus(status)
        await self._session.commit()
        await self._session.refresh(row)
        return _order_row_to_snapshot(row)

    async def update_status(self, *, order_id: UUID, status: str) -> OrderSnapshot | None:
        row = await self._load_row(order_id=order_id)
        if row is None:
            return None
        row.status = DbOrderStatus(status)
        await self._session.commit()
        await self._session.refresh(row)
        return _order_row_to_snapshot(row)

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
        status: str | None = None,
    ) -> tuple[list[OrderSnapshot], int]:
        conditions = [OrderRow.user_id == user_id]
        if status is not None:
            try:
                db_status = DbOrderStatus(status)
            except ValueError:
                return [], 0
            conditions.append(OrderRow.status == db_status)

        total_count_stmt = select(func.count()).select_from(OrderRow).where(*conditions)
        total_count = int((await self._session.execute(total_count_stmt)).scalar_one())
        if total_count == 0:
            return [], 0

        stmt = (
            select(OrderRow)
            .options(selectinload(OrderRow.items))
            .where(*conditions)
            .order_by(OrderRow.created_at.desc(), OrderRow.id.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_order_row_to_snapshot(row) for row in rows], total_count

    async def save(self, order: OrderSnapshot) -> OrderSnapshot:
        row = OrderRow(
            id=order.id,
            user_id=order.user_id,
            idempotency_key=order.idempotency_key,
            address_id=order.address_id,
            payment_method_id=order.payment_method_id,
            request_fingerprint=order.request_fingerprint,
            status=DomainOrderStatus(order.status.value),
            total_amount=order.total_amount,
            delivery_address=None,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
        self._session.add(row)
        for item in order.items:
            self._session.add(
                OrderItemRow(
                    id=item.id,
                    order_id=order.id,
                    sku_id=item.sku_id,
                    product_id=item.product_id,
                    product_title=item.product_title,
                    sku_name=item.sku_name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                    created_at=order.created_at,
                )
            )

        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self.get_by_idempotency_key(order.idempotency_key)
            if existing is not None:
                return existing
            raise

        return order

    async def _load_row(
        self,
        *,
        order_id: UUID,
        user_id: UUID | None = None,
    ) -> OrderRow | None:
        conditions = [OrderRow.id == order_id]
        if user_id is not None:
            conditions.append(OrderRow.user_id == user_id)
        stmt = select(OrderRow).options(selectinload(OrderRow.items)).where(*conditions).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()


class HttpCheckoutCatalogClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 5.0,
        service_key: str | None = None,
    ) -> None:
        self._base_url = (base_url or os.getenv("B2B_BASE_URL") or "http://localhost:8001").rstrip(
            "/"
        )
        self._timeout = timeout
        self._service_key = service_key or os.getenv("B2B_SERVICE_KEY")

    async def get_skus_by_ids(self, sku_ids: Iterable[UUID]) -> list[CatalogSkuSnapshot]:
        ids = [str(sku_id) for sku_id in sku_ids]
        payload = await self._get("/api/v1/products", [("ids", ",".join(ids))])
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise UpstreamServiceError("Unexpected upstream response", 502)
        skus: list[CatalogSkuSnapshot] = []
        for product in items:
            if not isinstance(product, dict):
                continue
            skus.extend(_parse_product_skus(product))
        wanted = {UUID(str(sku_id)) for sku_id in sku_ids}
        return [sku for sku in skus if sku.sku_id in wanted]

    async def reserve(
        self,
        *,
        order_id: UUID,
        idempotency_key: UUID,
        items: list[ReserveRequestItem],
    ) -> ReserveResult:
        payload = {
            "order_id": str(order_id),
            "idempotency_key": str(idempotency_key),
            "items": [{"sku_id": str(item.sku_id), "quantity": item.quantity} for item in items],
        }
        response_payload = await self._post(
            "/api/v1/inventory/reserve", payload, expected_statuses={200, 409}
        )
        reserved = bool(response_payload.get("reserved"))
        failed_items = tuple(
            _parse_failed_item(item) for item in response_payload.get("failed_items", []) or []
        )
        return ReserveResult(reserved=reserved, failed_items=failed_items)

    async def unreserve(
        self,
        *,
        order_id: UUID,
        items: list[ReserveRequestItem],
    ) -> None:
        payload = {
            "order_id": str(order_id),
            "items": [{"sku_id": str(item.sku_id), "quantity": item.quantity} for item in items],
        }
        await self._post("/api/v1/inventory/unreserve", payload, expected_statuses={200})

    async def fulfill(
        self,
        *,
        order_id: UUID,
        items: list[ReserveRequestItem],
    ) -> None:
        payload = {
            "order_id": str(order_id),
            "items": [{"sku_id": str(item.sku_id), "quantity": item.quantity} for item in items],
        }
        response_payload = await self._post(
            "/api/v1/inventory/fulfill", payload, expected_statuses={200}
        )
        if response_payload.get("status") != "FULFILLED":
            raise UpstreamServiceError("Unexpected upstream response", 502)

    async def _get(self, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {}
        if self._service_key:
            headers["X-Service-Key"] = self._service_key
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.RequestError as exc:
            raise UpstreamServiceError("B2B temporarily unavailable", None) from exc

        if response.status_code in {502, 503}:
            raise UpstreamServiceError("B2B temporarily unavailable", response.status_code)
        if response.status_code != 200:
            raise UpstreamServiceError("Unexpected upstream response", response.status_code)
        return response.json()

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        expected_statuses: set[int],
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self._service_key:
            headers["X-Service-Key"] = self._service_key
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise UpstreamServiceError("B2B temporarily unavailable", None) from exc

        if response.status_code in {502, 503, 504}:
            raise UpstreamServiceError("B2B temporarily unavailable", response.status_code)
        if response.status_code not in expected_statuses:
            raise UpstreamServiceError("Unexpected upstream response", response.status_code)
        payload = response.json()
        if not isinstance(payload, dict):
            raise UpstreamServiceError("Unexpected upstream response", response.status_code)
        return payload


def _parse_product_skus(payload: dict[str, Any]) -> list[CatalogSkuSnapshot]:
    product_id = UUID(str(payload["id"]))
    product_title = str(payload.get("title") or payload.get("name") or "")
    status = str(payload.get("status") or "MODERATED")
    deleted = bool(payload.get("deleted", False))
    skus_payload = payload.get("skus") or []
    skus: list[CatalogSkuSnapshot] = []
    for sku_payload in skus_payload:
        if not isinstance(sku_payload, dict):
            continue
        price = int(sku_payload.get("price", 0))
        discount = int(sku_payload.get("discount", 0))
        unit_price = price - discount if discount else price
        skus.append(
            CatalogSkuSnapshot(
                sku_id=UUID(str(sku_payload["id"])),
                product_id=product_id,
                product_title=product_title,
                sku_name=str(sku_payload.get("name") or ""),
                unit_price=unit_price,
                active_quantity=int(sku_payload.get("active_quantity", 0)),
                product_status=status,
                product_deleted=deleted,
            )
        )
    return skus


def _parse_failed_item(payload: dict[str, Any]) -> ReserveFailedItem:
    return ReserveFailedItem(
        sku_id=UUID(str(payload["sku_id"])),
        requested=int(payload.get("requested", 0)),
        available=int(payload.get("available", 0)),
        reason=str(payload.get("reason", "INSUFFICIENT_STOCK")),
    )


def _order_row_to_snapshot(row: OrderRow) -> OrderSnapshot:
    items = tuple(
        OrderItemSnapshot(
            id=item.id,
            sku_id=item.sku_id,
            product_id=item.product_id,
            product_title=item.product_title,
            sku_name=item.sku_name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
        )
        for item in row.items
    )
    return OrderSnapshot(
        id=row.id,
        user_id=row.user_id,
        idempotency_key=row.idempotency_key,
        address_id=row.address_id,
        payment_method_id=row.payment_method_id,
        request_fingerprint=row.request_fingerprint,
        status=DomainOrderStatus(row.status.value),
        items=items,
        total_amount=row.total_amount,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
