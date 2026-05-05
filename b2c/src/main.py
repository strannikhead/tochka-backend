from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api import cart, catalog, categories, favorites, home, products

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
app.include_router(cart.router)
app.include_router(favorites.router)
app.include_router(home.router)
