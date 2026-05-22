from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

ERROR_CODES = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    502: "UPSTREAM_ERROR",
    503: "UPSTREAM_ERROR",
}


def error_payload(
    status_code: int,
    message: str,
    *,
    code: str | None = None,
    details: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code or ERROR_CODES.get(status_code, "INTERNAL_ERROR"),
        "message": message,
    }
    if details is not None:
        payload["details"] = details
    return payload


def error_response(
    status_code: int,
    message: str,
    *,
    code: str | None = None,
    details: Any | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_payload(status_code, message, code=code, details=details),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, Mapping) and "code" in exc.detail and "message" in exc.detail:
        payload = dict(exc.detail)
        payload.setdefault("code", ERROR_CODES.get(exc.status_code, "INTERNAL_ERROR"))
        return JSONResponse(status_code=exc.status_code, content=payload)

    return error_response(exc.status_code, str(exc.detail))


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    message = "Validation error"
    errors = exc.errors()
    if errors:
        first_error = errors[0]
        message = str(first_error.get("msg") or first_error.get("type") or message)
    return error_response(400, message)
