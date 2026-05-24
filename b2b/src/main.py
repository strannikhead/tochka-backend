from b2b.src.api import categories, inventory, invoices, products, skus
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="B2B Seller Cabinet")

app.include_router(categories.router)
app.include_router(products.router)
app.include_router(products.public_router)
app.include_router(inventory.router)
app.include_router(skus.router)
app.include_router(invoices.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
