"""Fixtures for the application platform (FastAPI + Supabase).

DESTRUCTIVE: after every test the `db` fixture deletes every business (and, by cascade, all leads, activities and
users). TEST_SUPABASE_URL / TEST_SUPABASE_SECRET_KEY (env or `.env`) must therefore be a separate Supabase project
used only for tests, with `db/*.sql` pasted into its SQL editor. The fixture refuses the app's own project.

Database tests are skipped when the test project is not configured or not reachable, keeping the rest of the suite
runnable anywhere.
"""

import os
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import pytest
from fastapi import Header
from httpx import ASGITransport, AsyncClient
from supabase import AsyncClient as SupabaseClient
from supabase import acreate_client

# HACK: importing app.main builds the module-level ASGI app, whose create_app() loads Settings, and OPENAI_MODEL
# is a required field. Without this, the platform suite would depend on a developer `.env` being present.
os.environ.setdefault("OPENAI_MODEL", "test-model")

from app.core.auth import AuthUser, current_user
from app.core.supabase import get_supabase
from app.main import create_app
from settings import get_config

ROOT = Path(__file__).resolve().parents[2]
TEST_USER_ID = uuid.UUID(int=1)


def as_user(user_id: uuid.UUID) -> dict[str, str]:
    """Request headers that make the test app treat the caller as ``user_id`` instead of the default test user."""
    return {"x-test-user": str(user_id)}


def _test_user(x_test_user: Annotated[uuid.UUID | None, Header()] = None) -> AuthUser:
    user_id = x_test_user or TEST_USER_ID
    return AuthUser(id=user_id, email=f"{user_id}@example.com")


def _normalized(url: str) -> str:
    return url.strip().rstrip("/").lower()


def unsafe_test_project_reason(test_url: str, app_url: str | None) -> str | None:
    """Why `test_url` must not be used by the destructive fixtures, or None when it is a separate project."""
    if not _normalized(test_url).startswith("https://"):
        return "TEST_SUPABASE_URL must be a Supabase project URL (https://<ref>.supabase.co)"
    if app_url and _normalized(test_url) == _normalized(app_url):
        return "TEST_SUPABASE_URL is the app's own project (SUPABASE_PROJECT_URL); use a separate test project"
    return None


async def _delete_all(db: SupabaseClient) -> None:
    # PostgREST refuses an unfiltered DELETE; every real id differs from the nil UUID.
    await db.table("businesses").delete().neq("id", str(uuid.UUID(int=0))).execute()


@pytest.fixture
async def db() -> AsyncIterator[SupabaseClient]:
    config = get_config()
    if not config.TEST_SUPABASE_URL or not config.TEST_SUPABASE_SECRET_KEY:
        pytest.skip("TEST_SUPABASE_URL / TEST_SUPABASE_SECRET_KEY not set (a separate Supabase project for tests)")
    if reason := unsafe_test_project_reason(config.TEST_SUPABASE_URL, config.SUPABASE_PROJECT_URL):
        pytest.exit(f"Refusing to run destructive platform fixtures: {reason}", returncode=2)
    client = await acreate_client(config.TEST_SUPABASE_URL, config.TEST_SUPABASE_SECRET_KEY)
    try:
        await _delete_all(client)
    except Exception as exc:
        pytest.skip(f"Test Supabase project not usable ({exc}); did you paste db/*.sql into it?")
    yield client
    await _delete_all(client)


@asynccontextmanager
async def make_client(
    db: SupabaseClient,
    overrides: Mapping[Callable[..., Any], Callable[..., Any]] | None = None,
) -> AsyncIterator[AsyncClient]:
    """An HTTP client for a fresh app whose `get_supabase` dependency returns `db`.

    Requests are signed in as `TEST_USER_ID`; `as_user` headers switch to another user.

    `overrides` are extra FastAPI dependency overrides (e.g. a fixed clock), applied after the default ones.
    """
    app = create_app()

    async def _db() -> SupabaseClient:
        return db

    app.dependency_overrides[get_supabase] = _db
    app.dependency_overrides[current_user] = _test_user
    app.dependency_overrides.update(overrides or {})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def api_prefix() -> str:
    return get_config().api_prefix


@pytest.fixture
async def client(db: SupabaseClient) -> AsyncIterator[AsyncClient]:
    async with make_client(db) as client:
        yield client
