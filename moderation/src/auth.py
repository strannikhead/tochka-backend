"""Moderator authentication — HTTPBearer JWT, identity from 'sub' claim."""

from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# auto_error=False: missing/non-Bearer Authorization → 401, not FastAPI's default 403.
_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHORIZED", "message": message},
    )


def _moderator_id_from_token(token: str) -> UUID:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise _unauthorized("Невалидный токен") from exc

    raw = payload.get("sub") or payload.get("moderator_id")
    if raw is None:
        raise _unauthorized("В токене отсутствует идентификатор модератора")
    try:
        return UUID(str(raw))
    except ValueError as exc:
        raise _unauthorized("Некорректный идентификатор модератора в токене") from exc


def get_current_moderator_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UUID:
    """Decode the bearer JWT and return the moderator id from its claims."""
    if credentials is None:
        raise _unauthorized("Требуется авторизация")
    return _moderator_id_from_token(credentials.credentials)
