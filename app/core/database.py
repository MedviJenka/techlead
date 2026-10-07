from collections.abc import AsyncIterator
from functools import cache
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from settings import get_config


def build_engine(url: str, echo: bool = False) -> AsyncEngine:
    connect_args: dict[str, Any] = {}
    if "pooler.supabase.com" in url:
        # Supabase's PgBouncer (transaction mode) cannot keep prepared statements across transactions.
        connect_args["statement_cache_size"] = 0
    return create_async_engine(url, echo=echo, pool_pre_ping=True, connect_args=connect_args)


@cache
def get_engine() -> AsyncEngine:
    config = get_config()
    return build_engine(config.async_database_url, echo=config.DB_ECHO)


@cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request. Services own commit boundaries."""
    async with get_sessionmaker()() as session:
        yield session
