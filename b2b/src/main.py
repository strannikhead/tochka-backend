from fastapi import FastAPI

from api import invoices, products, skus

app = FastAPI(title="B2B Seller Cabinet")

app.include_router(products.router)
app.include_router(skus.router)
app.include_router(invoices.router)
