from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api import blocking_reasons, product_moderation
from errors import error_response
from modqueue.domain import ModeratorAlreadyInReviewError
from modqueue.router import router as queue_router

app = FastAPI(title="Moderation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(product_moderation.router)
app.include_router(blocking_reasons.router)
app.include_router(queue_router)

_STATUS_ERROR_CODES = {
    400: "INVALID_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = jsonable_encoder(exc.errors())
    first = errors[0] if errors else {}
    field = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    message = first.get("msg", "Невалидные данные")
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": f"{field}: {message}" if field else message,
            "details": {"errors": errors},
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail: Any = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        body: dict[str, Any] = {"code": detail["code"], "message": detail["message"]}
        if detail.get("details") is not None:
            body["details"] = detail["details"]
    else:
        body = {
            "code": _STATUS_ERROR_CODES.get(exc.status_code, "ERROR"),
            "message": detail if isinstance(detail, str) else "Ошибка запроса",
        }
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return error_response(500, "INTERNAL_ERROR", "Internal server error")


@app.exception_handler(ModeratorAlreadyInReviewError)
async def moderator_already_in_review_handler(
    request: Request, exc: ModeratorAlreadyInReviewError
) -> JSONResponse:
    return error_response(
        409, "MODERATOR_ALREADY_IN_REVIEW", "You already have an active ticket in review."
    )
