from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.blocking_reasons.domain import (
    BlockingReasonDTO,
    ReasonCodeExistsError,
    ReasonNotFoundError,
)
from api.blocking_reasons.repository import (
    BlockingReasonsRepositoryProtocol,
    DbBlockingReasonsRepository,
)
from auth import get_current_moderator_id
from database import AsyncSession, get_session
from errors import error_response

# Path per moderation/openapi.yaml (/blocking-reasons), not the canon's
# /product-blocking-reasons — the OpenAPI spec is the source of truth.
router = APIRouter(prefix="/api/v1/blocking-reasons", tags=["BlockingReasons"])


# ---- Schemas (mirror BlockingReason* in moderation/openapi.yaml) ----


class BlockingReasonResponse(BaseModel):
    id: UUID
    code: str
    title: str
    description: str | None = None
    hard_block: bool
    is_active: bool


class BlockingReasonCreateRequest(BaseModel):
    code: str = Field(pattern=r"^[A-Z_]+$", max_length=64)
    title: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    hard_block: bool


class BlockingReasonUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


def _to_response(dto: BlockingReasonDTO) -> BlockingReasonResponse:
    return BlockingReasonResponse(
        id=dto.id,
        code=dto.code,
        title=dto.title,
        description=dto.description,
        hard_block=dto.hard_block,
        is_active=dto.is_active,
    )


# ---- Dependency ----


def get_reasons_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BlockingReasonsRepositoryProtocol:
    return DbBlockingReasonsRepository(session)


# ---- Endpoints ----


@router.get("", response_model=list[BlockingReasonResponse])
async def list_blocking_reasons(
    repo: Annotated[BlockingReasonsRepositoryProtocol, Depends(get_reasons_repo)],
    hard_block: bool | None = Query(default=None),
    is_active: bool = Query(default=True),
) -> list[BlockingReasonResponse]:
    # Default returns only active reasons; pass is_active=false to see deactivated ones.
    reasons = await repo.list_reasons(hard_block=hard_block, is_active=is_active)
    return [_to_response(r) for r in reasons]


@router.post("", status_code=201, response_model=None)
async def create_blocking_reason(
    body: BlockingReasonCreateRequest,
    _moderator_id: Annotated[UUID, Depends(get_current_moderator_id)],
    repo: Annotated[BlockingReasonsRepositoryProtocol, Depends(get_reasons_repo)],
) -> BlockingReasonResponse | JSONResponse:
    try:
        dto = await repo.create(
            code=body.code,
            title=body.title,
            description=body.description,
            hard_block=body.hard_block,
        )
    except ReasonCodeExistsError:
        return error_response(409, "CONFLICT", f"Reason with code '{body.code}' already exists")
    return _to_response(dto)


@router.patch("/{reason_id}", response_model=None)
async def update_blocking_reason(
    reason_id: UUID,
    body: BlockingReasonUpdateRequest,
    _moderator_id: Annotated[UUID, Depends(get_current_moderator_id)],
    repo: Annotated[BlockingReasonsRepositoryProtocol, Depends(get_reasons_repo)],
) -> BlockingReasonResponse | JSONResponse:
    try:
        dto = await repo.update(
            reason_id,
            title=body.title,
            description=body.description,
            is_active=body.is_active,
        )
    except ReasonNotFoundError:
        return error_response(404, "NOT_FOUND", "Blocking reason not found")
    return _to_response(dto)


@router.delete("/{reason_id}", status_code=204, response_model=None)
async def deactivate_blocking_reason(
    reason_id: UUID,
    _moderator_id: Annotated[UUID, Depends(get_current_moderator_id)],
    repo: Annotated[BlockingReasonsRepositoryProtocol, Depends(get_reasons_repo)],
) -> Response | JSONResponse:
    # DELETE is a soft deactivation (is_active=false). Reasons are never physically
    # removed, so historical BLOCKED cards keep their FK reference (referential integrity).
    try:
        await repo.deactivate(reason_id)
    except ReasonNotFoundError:
        return error_response(404, "NOT_FOUND", "Blocking reason not found")
    return Response(status_code=204)
