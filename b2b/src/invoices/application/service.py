from __future__ import annotations

from typing import TYPE_CHECKING

from b2b.src.invoices.domain.models import CreateInvoiceCommand
from b2b.src.invoices.domain.repository import InvoicesRepository

if TYPE_CHECKING:
    from b2b.src.models import Invoice


class InvoicesService:
    def __init__(self, repository: InvoicesRepository) -> None:
        self._repository = repository

    async def create_invoice(self, command: CreateInvoiceCommand) -> Invoice:
        return await self._repository.create_invoice(command)
