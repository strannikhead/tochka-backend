from b2b.src.api import categories, inventory, invoices, products, skus
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="B2B Seller Cabinet")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Match the OpenAPI `Error` schema ({code, message, details}) on 422 instead of
    # FastAPI's default {detail: [...]} body.
    errors = jsonable_encoder(exc.errors())
    first = errors[0] if errors else {}
    field = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    message = first.get("msg", "Невалидные данные")
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": f"{field}: {message}" if field else message,
            "details": {"errors": errors},
        },
    )


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
