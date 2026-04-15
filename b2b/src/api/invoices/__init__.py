from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])


@router.post("")
async def create_invoice() -> dict[str, str]:
    return {"endpoint": "create_invoice"}


@router.post("/accept")
async def accept_invoice() -> dict[str, str]:
    return {"endpoint": "accept_invoice"}
