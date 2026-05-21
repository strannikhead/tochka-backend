from b2b.src.api import categories, invoices, products, public_catalog, skus
from fastapi import FastAPI

app = FastAPI(title="B2B Seller Cabinet")

app.include_router(categories.router)
app.include_router(products.router)
app.include_router(public_catalog.router)
app.include_router(skus.router)
app.include_router(invoices.router)
