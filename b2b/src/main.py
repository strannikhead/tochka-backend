from b2b.src.api import categories, inventory, invoices, moderation, products, skus
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(title="B2B Seller Cabinet")

# Map HTTP status codes to the `code` field of the OpenAPI `Error` schema.
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
    # Match the OpenAPI `Error` schema ({code, message, details}) on 422 instead of
    # FastAPI's default {detail: [...]} body.
    errors = jsonable_encoder(exc.errors())
    first = errors[0] if errors else {}
    field = ".".join(str(part) for part in first.get("loc", []) if part != "body")
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
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    # Normalize every HTTPException to the OpenAPI `Error` schema ({code, message,
    # details?}) instead of FastAPI's default {detail: ...}. Handlers that already raise
    # a dict detail with code+message (e.g. auth) are passed through unchanged.
    # `details` is omitted entirely when absent so the body stays {code, message}.
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        body = {"code": detail["code"], "message": detail["message"]}
        if detail.get("details") is not None:
            body["details"] = detail["details"]
    else:
        body = {
            "code": _STATUS_ERROR_CODES.get(exc.status_code, "ERROR"),
            "message": detail if isinstance(detail, str) else "Ошибка запроса",
        }
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


app.include_router(categories.router)
app.include_router(products.router)
app.include_router(products.public_router)
app.include_router(inventory.router)
app.include_router(skus.router)
app.include_router(invoices.router)
app.include_router(moderation.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
