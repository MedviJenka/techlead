"""The backend's only database access: one Supabase client per process, authenticated with the secret key."""

from typing import Any

from pydantic_core import to_jsonable_python
from supabase import AsyncClient, acreate_client

from settings import get_config

_client: AsyncClient | None = None


async def get_supabase() -> AsyncClient:
    """FastAPI dependency: the shared Supabase client, created on first use."""
    global _client
    if _client is None:
        url, key = get_config().supabase_credentials()
        _client = await acreate_client(url, key)
    return _client


def to_json(value: Any) -> Any:
    """UUIDs, datetimes, enums and sets as JSON values, ready to send through the client."""
    return to_jsonable_python(value)
