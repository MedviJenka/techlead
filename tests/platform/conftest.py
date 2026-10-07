"""Fixtures for the application platform (FastAPI + PostgreSQL).

DESTRUCTIVE: the session fixture runs `alembic downgrade base` (drops every table) and each test TRUNCATEs
`businesses`. It therefore refuses (`pytest.exit`) any TEST_DATABASE_URL whose database name does not end in
`_test` or whose host is Supabase (see `unsafe_test_database_reason`). Never point it at real data.

Runs against a real PostgreSQL (`docker compose up -d db` provides `techlead_test` on :5433). The schema is
built with the Alembic migrations, so these tests also verify that migrations match the models.
Tests are skipped when the database is unreachable, keeping the AI-layer suite runnable anywhere.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# HACK: importing app.main builds the module-level ASGI app, whose create_app() loads Settings, and OPENAI_MODEL
# is a required field. Without this, the platform suite would depend on a developer `.env` being present.
os.environ.setdefault("OPENAI_MODEL", "test-model")

from app.core.database import get_session
from app.main import create_app
from settings import get_config

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://techlead:techlead@localhost:5433/techlead_test"
)
ROOT = Path(__file__).resolve().parents[2]
_SUPABASE_HOST_SUFFIXES = (".supabase.co", ".supabase.com")


def unsafe_test_database_reason(url: str) -> str | None:
    """Why `url` must not be used by the destructive fixtures, or None when it is a dedicated test database."""
    try:
        parsed = make_url(url)
    except ArgumentError:
        return f"TEST_DATABASE_URL is not a valid SQLAlchemy URL: {url!r}"
    host = (parsed.host or "").lower()
    if host.endswith(_SUPABASE_HOST_SUFFIXES) or "pooler" in host:
        return f"TEST_DATABASE_URL points at Supabase host {host!r}; tests must use a local database"
    if not (parsed.database or "").endswith("_test"):
        return f"TEST_DATABASE_URL database {parsed.database!r} must end with '_test'"
    return None


async def _database_reachable() -> bool:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    if reason := unsafe_test_database_reason(TEST_DATABASE_URL):
        pytest.exit(f"Refusing to run destructive platform fixtures: {reason}", returncode=2)
    if not asyncio.run(_database_reachable()):
        pytest.skip(f"PostgreSQL not reachable at {TEST_DATABASE_URL} (run `docker compose up -d db`)")
    # No config file: alembic's fileConfig would reset logging for the rest of the session.
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield TEST_DATABASE_URL


@pytest.fixture
async def engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE businesses CASCADE"))
    await engine.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as session:
        yield session


@asynccontextmanager
async def make_client(
    session_factory: Callable[[], AsyncSession],
    overrides: Mapping[Callable[..., Any], Callable[..., Any]] | None = None,
) -> AsyncIterator[AsyncClient]:
    """An HTTP client for a fresh app whose `get_session` dependency yields sessions from `session_factory`.

    `overrides` are extra FastAPI dependency overrides (e.g. a fixed clock), applied after the session one.
    """
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides.update(overrides or {})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def api_prefix() -> str:
    return get_config().api_prefix


@pytest.fixture
async def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    async with make_client(sessionmaker) as client:
        yield client
