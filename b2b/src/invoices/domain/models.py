from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class InvoiceItemInput:
    sku_id: UUID
    quantity: int


@dataclass(frozen=True)
class CreateInvoiceCommand:
    """Validated input for creating an invoice; seller_id comes from the JWT."""

    seller_id: UUID
    items: tuple[InvoiceItemInput, ...]
