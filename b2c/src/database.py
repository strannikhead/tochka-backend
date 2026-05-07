from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DEFAULT_URL = "postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_b2c"


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", _DEFAULT_URL)
    # docker-compose передаёт postgresql://, asyncpg требует postgresql+psycopg://
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


engine = create_async_engine(_database_url(), pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
