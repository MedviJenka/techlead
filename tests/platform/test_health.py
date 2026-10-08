from httpx import AsyncClient
from supabase import acreate_client

from tests.platform.conftest import make_client


async def test_health_ok(client: AsyncClient, api_prefix: str) -> None:
    response = await client.get(f"{api_prefix}/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_health_degraded_when_database_down(api_prefix: str) -> None:
    unreachable = await acreate_client("http://127.0.0.1:1", "sb_secret_unreachable")
    async with make_client(unreachable) as client:
        response = await client.get(f"{api_prefix}/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
