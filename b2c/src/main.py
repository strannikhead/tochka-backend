from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.api import cart, catalog, categories, collections, favorites, home, orders, products

app = FastAPI(title="B2C (catalog, cart, favorites, home)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(categories.router)
app.include_router(catalog.router)
app.include_router(collections.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(favorites.router)
app.include_router(home.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    if exc.status_code == 401:
        return JSONResponse(
            status_code=401, content={"code": "UNAUTHORIZED", "message": str(exc.detail)}
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
