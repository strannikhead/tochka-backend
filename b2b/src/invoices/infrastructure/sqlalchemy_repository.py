from __future__ import annotations

from b2b.src.invoices.domain.errors import (
    EmptyInvoiceError,
    InvoiceSkuNotFoundError,
    InvoiceSkuNotModeratedError,
    InvoiceSkuNotOwnedError,
)
from b2b.src.invoices.domain.models import CreateInvoiceCommand
from b2b.src.models import SKU, Invoice, InvoiceItem, InvoiceStatus, ProductStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class SqlAlchemyInvoicesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_invoice(self, command: CreateInvoiceCommand) -> Invoice:
        if not command.items:
            raise EmptyInvoiceError("Invoice must contain at least one item")

        # Business validation lives here (server-side), so it cannot be bypassed by a
        # different serializer or a future endpoint that reuses the model (see PR ADR).
        for item in command.items:
            stmt = select(SKU).where(SKU.id == item.sku_id).options(selectinload(SKU.product))
            sku = (await self._session.execute(stmt)).scalar_one_or_none()
            if sku is None or sku.product is None:
                raise InvoiceSkuNotFoundError(f"SKU {item.sku_id} not found")
            # Ownership first (403) so another seller's SKU never leaks its status.
            if sku.product.seller_id != command.seller_id:
                raise InvoiceSkuNotOwnedError(f"SKU {item.sku_id} belongs to another seller")
            if sku.product.deleted or sku.product.status != ProductStatus.MODERATED:
                raise InvoiceSkuNotModeratedError(f"SKU {item.sku_id} product is not MODERATED")

        invoice = Invoice(seller_id=command.seller_id, status=InvoiceStatus.CREATED)
        invoice.items = [
            InvoiceItem(sku_id=item.sku_id, quantity=item.quantity, accepted_quantity=0)
            for item in command.items
        ]
        self._session.add(invoice)
        await self._session.commit()
        return invoice
