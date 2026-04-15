from fastapi import FastAPI

from api import cart, catalog, categories, favorites, home, products

app = FastAPI(title="B2C (catalog, cart, favorites, home)")

app.include_router(products.router)
app.include_router(categories.router)
app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(favorites.router)
app.include_router(home.router)
