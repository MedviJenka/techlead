"""Fixtures for the application platform (FastAPI + PostgreSQL).

Runs against a real PostgreSQL (`docker compose up -d db` provides `techlead_test` on :5433). The schema is
built with the Alembic migrations, so these tests also verify that migrations match the models.
Tests are skipped when the database is unreachable, keeping the AI-layer suite runnable anywhere.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ.setdefault("OPENAI_MODEL", "test-model")

from app.core.database import get_session
from app.main import create_app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://techlead:techlead@localhost:5433/techlead_test"
)
ROOT = Path(__file__).resolve().parents[2]


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


@pytest.fixture
async def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
