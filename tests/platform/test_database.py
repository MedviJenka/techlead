"""Engine configuration and ORM round-trip guarantees of the persistence layer."""

from typing import Any

import pytest
from sqlalchemy import event, inspect
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from app.core.database import build_engine
from app.models import Business
from app.repositories import BusinessRepository

URL = "postgresql+asyncpg://user:secret@db.invalid:6543/postgres"


class _ConnectIntercepted(Exception):
    pass


async def _connect_params(engine: AsyncEngine) -> dict[str, Any]:
    """Capture the keyword arguments the dialect would pass to asyncpg, without opening a connection."""
    captured: dict[str, Any] = {}

    @event.listens_for(engine.sync_engine, "do_connect")
    def _intercept(dialect: Dialect, conn_rec: object, cargs: tuple[Any, ...], cparams: dict[str, Any]) -> None:
        captured.update(cparams)
        raise _ConnectIntercepted

    with pytest.raises(_ConnectIntercepted):
        async with engine.connect():
            pass
    await engine.dispose()
    return captured


async def test_default_engine_pools_and_caches_statements() -> None:
    engine = build_engine(URL)

    assert isinstance(engine.pool, AsyncAdaptedQueuePool)
    params = await _connect_params(engine)
    assert "statement_cache_size" not in params
    assert "prepared_statement_cache_size" not in params
    assert "prepared_statement_name_func" not in params


async def test_transaction_pooler_engine_disables_prepared_statement_reuse() -> None:
    engine = build_engine(URL, transaction_pooler=True)

    assert isinstance(engine.pool, NullPool)
    params = await _connect_params(engine)
    assert params["statement_cache_size"] == 0
    assert params["prepared_statement_cache_size"] == 0
    name_func = params["prepared_statement_name_func"]
    first, second = name_func(), name_func()
    assert first != second
    assert first.startswith("__asyncpg_") and first.endswith("__")


def _loaded(business: Business, *attributes: str) -> bool:
    unloaded = inspect(business).unloaded
    return not any(attribute in unloaded for attribute in attributes)


async def test_add_populates_server_defaults_without_refresh(session: AsyncSession) -> None:
    business = await BusinessRepository(session).add(Business(name="Acme", slug="acme"))

    # Reading an unloaded attribute would lazy-load, which raises MissingGreenlet on AsyncSession.
    assert _loaded(business, "id", "created_at", "updated_at")
    assert business.created_at is not None
    assert business.updated_at is not None


async def test_update_flush_fetches_updated_at(session: AsyncSession) -> None:
    business = await BusinessRepository(session).add(Business(name="Acme", slug="acme"))
    await session.commit()
    created_updated_at = business.updated_at

    business.name = "Acme Ltd"
    await session.flush()

    assert _loaded(business, "updated_at")
    assert business.updated_at > created_updated_at
    await session.commit()
