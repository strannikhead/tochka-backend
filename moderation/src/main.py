from fastapi import FastAPI

from api import blocking_reasons, product_moderation

app = FastAPI(title="Moderation")

app.include_router(product_moderation.router)
app.include_router(blocking_reasons.router)
