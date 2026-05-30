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


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
        return error_response(
            exc.status_code,
            str(exc.detail["code"]),
            str(exc.detail["message"]),
        )
    if exc.status_code == 401:
        code = "UNAUTHORIZED"
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code in {400, 422}:
        code = "INVALID_REQUEST"
    elif exc.status_code in {502, 503}:
        code = "UPSTREAM_UNAVAILABLE"
    else:
        code = "HTTP_ERROR"
    return error_response(exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    message = exc.errors()[0]["msg"] if exc.errors() else "Invalid request"
    return error_response(422, "INVALID_REQUEST", message)


@app.exception_handler(Exception)
async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return error_response(500, "INTERNAL_ERROR", "Internal server error")
