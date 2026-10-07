from collections.abc import AsyncIterator
from functools import cache
from typing import Any
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from settings import get_config


def _unique_statement_name() -> str:
    return f"__asyncpg_{uuid4()}__"


def build_engine(url: str, echo: bool = False, *, transaction_pooler: bool = False) -> AsyncEngine:
    """Create the async engine.

    `transaction_pooler` must be set when `url` points at a transaction-mode pooler (Supabase Supavisor or
    PgBouncer on port 6543). Such a pooler hands each transaction to an arbitrary backend, so prepared
    statements must not be cached or reused by name, and pooling again on our side only holds idle slots.
    """
    kwargs: dict[str, Any] = {"echo": echo, "pool_pre_ping": True}
    if transaction_pooler:
        kwargs["connect_args"] = {
            "statement_cache_size": 0,  # asyncpg's own statement cache
            "prepared_statement_cache_size": 0,  # SQLAlchemy asyncpg dialect's cache
            "prepared_statement_name_func": _unique_statement_name,  # no name collisions across backends
        }
        kwargs["poolclass"] = NullPool
    return create_async_engine(url, **kwargs)


@cache
def get_engine() -> AsyncEngine:
    config = get_config()
    return build_engine(config.async_database_url, echo=config.DB_ECHO, transaction_pooler=config.DB_TRANSACTION_POOLER)


@cache
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request. Services own commit boundaries."""
    async with get_session_maker()() as session:
        yield session
