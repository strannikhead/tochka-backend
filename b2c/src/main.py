from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.api import (
    cart,
    catalog,
    category_navigation,
    collections,
    events,
    favorites,
    home,
    orders,
    products,
)

from b2c.src.api.errors import error_response

app = FastAPI(title="B2C (catalog, cart, favorites, home)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
if hasattr(products, "legacy_router"):
    app.include_router(products.legacy_router)
app.include_router(category_navigation.router)
if hasattr(category_navigation, "legacy_router"):
    app.include_router(category_navigation.legacy_router)
app.include_router(catalog.router)
if hasattr(catalog, "legacy_router"):
    app.include_router(catalog.legacy_router)
app.include_router(collections.router)
app.include_router(cart.router)
app.include_router(events.router)
app.include_router(orders.router)
app.include_router(favorites.router)
app.include_router(home.router)
if hasattr(home, "legacy_router"):
    app.include_router(home.legacy_router)


def _http_exception_code(status_code: int) -> str:
    if status_code == 400:
        return "INVALID_REQUEST"
    if status_code == 401:
        return "UNAUTHORIZED"
    if status_code == 403:
        return "FORBIDDEN"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 409:
        return "CONFLICT"
    if status_code == 422:
        return "VALIDATION_ERROR"
    if status_code >= 500:
        return "INTERNAL_ERROR"
    return "HTTP_ERROR"


def _http_exception_details(status_code: int, detail: Any) -> tuple[str, str]:
    if isinstance(detail, dict):
        code = detail.get("code")
        message = detail.get("message")

        if isinstance(code, str) and isinstance(message, str):
            return code, message

    return _http_exception_code(status_code), str(detail)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    _: Request, __: RequestValidationError
) -> JSONResponse:
    return error_response(422, code="VALIDATION_ERROR", message="Некорректный запрос")


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    code, message = _http_exception_details(exc.status_code, exc.detail)

    return error_response(
        exc.status_code,
        code=code,
        message=message,
    )


@app.exception_handler(Exception)
async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return error_response(500, "INTERNAL_ERROR", "Internal server error")
