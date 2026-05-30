from __future__ import annotations

from typing import Annotated

from b2b.src.db import get_session
from b2b.src.invoices.application.service import InvoicesService
from b2b.src.invoices.domain.repository import InvoicesRepository
from b2b.src.invoices.infrastructure.sqlalchemy_repository import SqlAlchemyInvoicesRepository
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession


def get_invoices_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InvoicesRepository:
    return SqlAlchemyInvoicesRepository(session)


def get_invoices_service(
    repository: Annotated[InvoicesRepository, Depends(get_invoices_repository)],
) -> InvoicesService:
    return InvoicesService(repository)
