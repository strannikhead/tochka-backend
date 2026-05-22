from fastapi import FastAPI
from src.api import categories, invoices, products, public_catalog, skus

app = FastAPI(title="B2B Seller Cabinet")

app.include_router(categories.router)
app.include_router(products.router)
app.include_router(public_catalog.router)
app.include_router(skus.router)
app.include_router(invoices.router)
