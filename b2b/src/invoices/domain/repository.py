from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from b2b.src.invoices.domain.models import CreateInvoiceCommand

if TYPE_CHECKING:
    from b2b.src.models import Invoice


class InvoicesRepository(Protocol):
    async def create_invoice(self, command: CreateInvoiceCommand) -> Invoice: ...
