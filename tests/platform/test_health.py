from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests.platform.conftest import make_client


async def test_health_ok(client: AsyncClient, api_prefix: str) -> None:
    response = await client.get(f"{api_prefix}/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_health_degraded_when_database_down(api_prefix: str) -> None:
    engine = create_async_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none", poolclass=NullPool)
    try:
        async with make_client(async_sessionmaker(engine)) as client:
            response = await client.get(f"{api_prefix}/health")
    finally:
        await engine.dispose()

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
