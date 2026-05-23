from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])


@router.post("")
async def create_invoice() -> dict[str, str]:
    return {"endpoint": "create_invoice"}


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
