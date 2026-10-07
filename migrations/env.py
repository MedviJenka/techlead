import asyncio
import logging
from logging.config import fileConfig
from alembic import context
from sqlalchemy.engine import Connection, make_url
from app.core.database import build_engine
from app.models import Base
from settings import get_config

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

target_metadata = Base.metadata


def _target() -> tuple[str, bool]:
    """Return (url, transaction_pooler).

    Tests and tooling may pass an explicit URL via `alembic -x url=...` or Config.set_main_option; such a URL
    is used as-is with plain pooling. Otherwise the application database (Supabase) from settings is the target.
    """
    override = context.get_x_argument(as_dictionary=True).get("url") or config.get_main_option("sqlalchemy.url")
    if override:
        return override, False
    settings = get_config()
    return settings.async_database_url, settings.DB_TRANSACTION_POOLER


def _describe(url: str) -> str:
    """host:port/database only, so credentials never reach the log."""
    parsed = make_url(url)
    return f"{parsed.host}:{parsed.port or 5432}/{parsed.database}"


def run_migrations_offline() -> None:
    url, _ = _target()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url, transaction_pooler = _target()
    # WARNING level on purpose: without `-x url=...` this is the real Supabase database.
    logger.warning("Alembic target database: %s (transaction_pooler=%s)", _describe(url), transaction_pooler)
    engine = build_engine(url, transaction_pooler=transaction_pooler)
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
