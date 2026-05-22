from b2c.src.api import cart, catalog, categories, favorites, home, products
from b2c.src.api.errors import http_exception_handler, validation_exception_handler
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

app = FastAPI(title="B2C (catalog, cart, favorites, home)")

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(products.router)
app.include_router(products.legacy_router)
app.include_router(categories.router)
app.include_router(categories.legacy_router)
app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(cart.legacy_router)
app.include_router(favorites.router)
app.include_router(favorites.legacy_router)
app.include_router(home.router)
app.include_router(home.legacy_router)
