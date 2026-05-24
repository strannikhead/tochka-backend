from __future__ import annotations

import os
from typing import Annotated, Any, Protocol
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.products.dependencies import get_product_repository
from src.database import get_session
from src.favorites.repository import DbFavoriteRepository, FavoriteRepository
from src.favorites.service import FavoritesService
from src.product_card.repository import ProductRepository


class ProductNotFoundError(Exception):
    """Raised when product is not found in B2B."""


class ProductServiceError(Exception):
    """Raised when B2B product service is unavailable or returns unexpected response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProductClient(Protocol):
    """Product client interface."""

    async def get_product(self, product_id: UUID) -> dict[str, Any]: ...


class HttpProductClient:
    """HTTP client for B2B products."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 5.0,
        service_key: str | None = None,
    ) -> None:
        self._base_url = (base_url or os.getenv("B2B_BASE_URL") or "http://localhost:8001").rstrip(
            "/"
        )
        self._timeout = timeout
        self._service_key = service_key or os.getenv("B2B_SERVICE_KEY")

    async def get_product(self, product_id: UUID) -> dict[str, Any]:
        """Get product by id from B2B."""

        url = f"{self._base_url}/api/v1/products/{product_id}"
        headers: dict[str, str] = {}

        if self._service_key:
            headers["X-Service-Key"] = self._service_key

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise ProductServiceError("Unable to reach B2B", None) from exc

        if response.status_code == 404:
            raise ProductNotFoundError() from None

        if response.status_code in {502, 503, 504}:
            raise ProductServiceError(
                "B2B temporarily unavailable",
                response.status_code,
            )

        if response.status_code >= 500:
            raise ProductServiceError(
                "B2B temporarily unavailable",
                response.status_code,
            )

        if response.status_code >= 400:
            raise ProductServiceError(
                "Unexpected B2B response",
                response.status_code,
            )

        return response.json()


def get_favorite_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FavoriteRepository:
    return DbFavoriteRepository(session)


def get_favorites_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FavoriteRepository:
    """Compatibility alias for cherry-picked code."""

    return get_favorite_repository(session)


def get_favorites_service(
    favorite_repo: Annotated[FavoriteRepository, Depends(get_favorite_repository)],
    product_repo: Annotated[ProductRepository, Depends(get_product_repository)],
) -> FavoritesService:
    return FavoritesService(favorite_repo, product_repo)


def get_product_client() -> ProductClient:
    """Return B2B product client."""

    return HttpProductClient()


def get_current_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> UUID:
    """Extract current user id from Bearer JWT."""

    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен отсутствует или невалиден",
        )

    token = authorization.removeprefix("Bearer ").strip()

    jwt_secret = os.getenv("JWT_SECRET", os.getenv("JWT_SECRET_KEY", "dev-secret"))
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")

    try:
        payload = jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен отсутствует или невалиден",
        ) from exc

    user_id_raw = payload.get("sub") or payload.get("user_id") or payload.get("userId")

    if user_id_raw is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен отсутствует или невалиден",
        )

    try:
        return UUID(str(user_id_raw))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен отсутствует или невалиден",
        ) from exc
