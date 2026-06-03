from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from b2b.src.products.application.service import ProductsService
from b2b.src.products.dependencies import get_products_service
from b2b.src.products.domain.models import FieldReportInput, ModerationDecision

router = APIRouter(prefix="/api/v1/moderation", tags=["moderation-events"])

SERVICE_KEY = os.getenv("B2B_SERVICE_KEY", "dev-service-key")

# Inbound events on this endpoint always come from the Moderation Service; the
# idempotency key is scoped under this sender.
SENDER_SERVICE = "moderation"


def _require_service_key(service_key: str | None) -> None:
    if service_key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail="Invalid service key")


class FieldReportPayload(BaseModel):
    field_name: str
    comment: str
    sku_id: UUID | None = None


class ModerationEventRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    idempotency_key: UUID
    product_id: UUID
    event_type: Literal["MODERATED", "BLOCKED"]
    moderator_id: UUID | None = None
    moderator_comment: str | None = None
    blocking_reason_id: UUID | None = None
    # Human-readable reason name (canon: Moderation sends it with the BLOCKED event).
    # Optional — the flat OpenAPI event does not declare it yet, so absence is tolerated.
    blocking_reason_title: str | None = None
    hard_block: bool = False
    field_reports: list[FieldReportPayload] | None = None
    occurred_at: datetime


def _invalid_request(message: str) -> JSONResponse:
    # The spec defines this endpoint's invalid-body response as 400 (not retryable),
    # so body validation is done manually rather than via the 422 request handler.
    return JSONResponse(status_code=400, content={"code": "INVALID_REQUEST", "message": message})


@router.post("/events", status_code=204)
async def receive_moderation_event(
    request: Request,
    service: Annotated[ProductsService, Depends(get_products_service)],
    x_service_key: str | None = Header(None, alias="X-Service-Key"),
) -> Response:
    # Service-to-service auth first: only the Moderation Service may post decisions.
    _require_service_key(x_service_key)

    try:
        raw = await request.json()
    except ValueError:
        return _invalid_request("Body must be valid JSON")
    try:
        body = ModerationEventRequest.model_validate(raw)
    except ValidationError as exc:
        return _invalid_request(f"Invalid moderation event: {exc.error_count()} error(s)")

    if body.event_type == "BLOCKED" and body.blocking_reason_id is None:
        # blocking_reason_id is mandatory for BLOCKED; a malformed event must not retry.
        return JSONResponse(
            status_code=400,
            content={
                "code": "INVALID_REQUEST",
                "message": "blocking_reason_id is required for BLOCKED",
            },
        )

    decision = ModerationDecision(
        idempotency_key=body.idempotency_key,
        product_id=body.product_id,
        event_type=body.event_type,
        hard_block=body.hard_block,
        blocking_reason_id=body.blocking_reason_id,
        blocking_reason_title=body.blocking_reason_title,
        moderator_comment=body.moderator_comment,
        field_reports=tuple(
            FieldReportInput(field_name=fr.field_name, comment=fr.comment, sku_id=fr.sku_id)
            for fr in (body.field_reports or [])
        ),
        sender_service=SENDER_SERVICE,
    )
    # 204 whether newly applied or a recognised duplicate (idempotent, no side effects).
    await service.apply_moderation_event(decision)
    return Response(status_code=204)
