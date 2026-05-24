"""Seller authentication for the B2B cabinet.

The OpenAPI security scheme is ``HTTPBearer`` with a JWT. The seller identity is
derived *only* from the token claims and never from the request body — this is the
IDOR guard for product creation and every other seller-scoped write.
"""

from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

_bearer_scheme = HTTPBearer(auto_error=True)
_optional_bearer_scheme = HTTPBearer(auto_error=False)


def _seller_id_from_token(token: str) -> UUID:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный токен"
        ) from exc

    raw_seller_id = payload.get("sub") or payload.get("seller_id")
    if raw_seller_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="В токене отсутствует идентификатор продавца",
        )
    try:
        return UUID(str(raw_seller_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректный идентификатор продавца в токене",
        ) from exc


def get_current_seller_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> UUID:
    """Decode the bearer JWT and return the seller id from its claims."""
    return _seller_id_from_token(credentials.credentials)


def get_optional_seller_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_optional_bearer_scheme)],
) -> UUID | None:
    """Seller id when a bearer token is present, else None (e.g. X-Service-Key calls)."""
    if credentials is None:
        return None
    return _seller_id_from_token(credentials.credentials)
