from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from b2b.src.auth import get_current_seller_id
from b2b.src.invoices.application.service import InvoicesService
from b2b.src.invoices.dependencies import get_invoices_service
from b2b.src.invoices.domain.errors import (
    EmptyInvoiceError,
    InvoiceSkuNotFoundError,
    InvoiceSkuNotModeratedError,
    InvoiceSkuNotOwnedError,
)
from b2b.src.invoices.domain.models import CreateInvoiceCommand, InvoiceItemInput
from b2b.src.models import Invoice

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])


class InvoiceItemPayload(BaseModel):
    sku_id: UUID
    quantity: int = Field(ge=1)


class InvoiceCreateRequest(BaseModel):
    # seller_id is never taken from the body — it comes from the JWT (IDOR guard).
    model_config = ConfigDict(extra="ignore")

    items: list[InvoiceItemPayload] = Field(default_factory=list)


def _serialize_invoice(invoice: Invoice) -> dict[str, object]:
    return {
        "id": str(invoice.id),
        "seller_id": str(invoice.seller_id),
        "status": invoice.status.value,
        "items": [
            {
                "id": str(item.id),
                "sku_id": str(item.sku_id),
                "quantity": item.quantity,
                "accepted_quantity": item.accepted_quantity,
            }
            for item in invoice.items
        ],
        "created_at": invoice.created_at.isoformat(),
        "updated_at": invoice.updated_at.isoformat(),
        "accepted_at": invoice.accepted_at.isoformat() if invoice.accepted_at else None,
        "accepted_by": str(invoice.accepted_by) if invoice.accepted_by else None,
    }


def _bad_request(message: str) -> JSONResponse:
    return JSONResponse(status_code=400, content={"code": "INVALID_REQUEST", "message": message})


@router.post("", status_code=201)
async def create_invoice(
    body: InvoiceCreateRequest,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[InvoicesService, Depends(get_invoices_service)],
) -> JSONResponse:
    command = CreateInvoiceCommand(
        seller_id=seller_id,
        items=tuple(
            InvoiceItemInput(sku_id=item.sku_id, quantity=item.quantity) for item in body.items
        ),
    )
    try:
        invoice = await service.create_invoice(command)
    except EmptyInvoiceError:
        return _bad_request("Invoice must contain at least one item")
    except InvoiceSkuNotOwnedError:
        return JSONResponse(
            status_code=403,
            content={"code": "NOT_OWNER", "message": "SKU belongs to another seller"},
        )
    except InvoiceSkuNotModeratedError:
        return _bad_request("All SKUs must belong to a MODERATED product")
    except InvoiceSkuNotFoundError:
        return _bad_request("One or more SKUs do not exist")

    return JSONResponse(status_code=201, content=_serialize_invoice(invoice))


@router.get("")
async def list_invoices(
    limit: int = 20, offset: int = 0, status: str | None = None
) -> dict[str, str]:
    return {"endpoint": "list_invoices"}


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: str) -> dict[str, str]:
    return {"endpoint": "get_invoice"}


@router.delete("/{invoice_id}")
async def delete_invoice(invoice_id: str) -> dict[str, str]:
    return {"endpoint": "delete_invoice"}


@router.post("/{invoice_id}/accept")
async def accept_invoice(invoice_id: str) -> dict[str, str]:
    return {"endpoint": "accept_invoice"}
