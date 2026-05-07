from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_security = HTTPBearer()
_JWT_SECRET = os.getenv("JWT_SECRET", "")
_JWT_ALGORITHMS = ["HS256"]


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_security)],
) -> UUID:
    secret = _JWT_SECRET or os.getenv("JWT_SECRET", "")
    try:
        payload = jwt.decode(
            credentials.credentials,
            secret or "dev",
            algorithms=_JWT_ALGORITHMS,
            options={"verify_exp": False, "verify_signature": bool(secret)},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Невалидный токен") from exc

    raw = payload.get("sub") or payload.get("user_id")
    if not raw:
        raise HTTPException(status_code=401, detail="Токен не содержит идентификатор пользователя")

    try:
        return UUID(str(raw))
    except ValueError as exc:
        raise HTTPException(
            status_code=401, detail="Некорректный идентификатор пользователя в токене"
        ) from exc
