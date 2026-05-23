from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_security = HTTPBearer(auto_error=False)
_JWT_SECRET = os.getenv("JWT_SECRET")
_JWT_ALGORITHMS = ["HS256"]


def _decode_user_id(token: str) -> UUID:
    if not _JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT_SECRET не настроен")
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=_JWT_ALGORITHMS)
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


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_security)],
) -> UUID:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return _decode_user_id(credentials.credentials)


async def get_optional_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_security)],
) -> UUID | None:
    if credentials is None:
        return None
    return _decode_user_id(credentials.credentials)
