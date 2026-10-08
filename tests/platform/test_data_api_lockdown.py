"""The publishable key must not reach the tables: only the backend (secret key) may read or write them.

`db/003_lock_down_data_api.sql` enables RLS with no policies and revokes every grant from `anon`/`authenticated`.
The static tests check that every table in `db/*.sql` is listed there. The live tests sign in to the test project
with TEST_SUPABASE_PUBLISHABLE_KEY and check that a seeded row can be neither read nor changed.
"""

import re
import uuid
from collections.abc import AsyncIterator

import pytest
from postgrest.exceptions import APIError
from supabase import AsyncClient, acreate_client

from settings import get_config
from tests.platform.conftest import ROOT
from tests.platform.factories import make_activity, make_business, make_lead

LOCKDOWN = (ROOT / "db" / "003_lock_down_data_api.sql").read_text(encoding="utf-8")
SQL = "\n".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "db").glob("*.sql")))
TABLES = sorted(set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SQL)))


def _revoked_tables() -> set[str]:
    match = re.search(r"REVOKE ALL ON TABLE (.*?) FROM anon, authenticated;", LOCKDOWN)
    assert match, "REVOKE ... FROM anon, authenticated not found in db/003_lock_down_data_api.sql"
    return {name.strip() for name in match.group(1).split(",")}


def test_tables_are_found() -> None:
    assert {"businesses", "leads", "activities", "users"} <= set(TABLES)


@pytest.mark.parametrize("table", TABLES)
def test_every_table_has_row_level_security(table: str) -> None:
    assert re.search(rf"ALTER TABLE {table}\s+ENABLE ROW LEVEL SECURITY;", LOCKDOWN)


@pytest.mark.parametrize("table", TABLES)
def test_every_table_is_revoked_from_the_publishable_key(table: str) -> None:
    assert table in _revoked_tables()


@pytest.fixture
async def public(db: AsyncClient) -> AsyncIterator[AsyncClient]:
    """A client of the test project signed with the publishable key (what a browser gets)."""
    config = get_config()
    if not config.TEST_SUPABASE_PUBLISHABLE_KEY:
        pytest.skip("TEST_SUPABASE_PUBLISHABLE_KEY not set (publishable key of the test Supabase project)")
    assert config.TEST_SUPABASE_URL  # checked by the `db` fixture
    yield await acreate_client(config.TEST_SUPABASE_URL, config.TEST_SUPABASE_PUBLISHABLE_KEY)


@pytest.fixture
async def seeded(db: AsyncClient) -> dict[str, str]:
    """One row in every table, written with the secret key; table -> row id."""
    business = await make_business(db)
    lead = await make_lead(db, business)
    activity = await make_activity(db, lead)
    user_id = uuid.uuid4()
    await db.table("users").insert({"id": str(user_id), "business_id": str(business.id), "email": "a@b.co"}).execute()
    return {
        "businesses": str(business.id),
        "leads": str(lead.id),
        "activities": str(activity.id),
        "users": str(user_id),
    }


async def _rows(client: AsyncClient, table: str) -> list[dict[str, object]] | None:
    """The rows `client` can see, or None when the request is refused."""
    try:
        response = await client.table(table).select("*").execute()
    except APIError:
        return None
    return list(response.data)


async def test_publishable_key_cannot_read(public: AsyncClient, seeded: dict[str, str]) -> None:
    for table in seeded:
        assert not await _rows(public, table), f"publishable key can read {table}"


async def test_publishable_key_cannot_insert(public: AsyncClient, db: AsyncClient, seeded: dict[str, str]) -> None:
    with pytest.raises(APIError):
        await public.table("businesses").insert({"name": "Intruder", "slug": "intruder"}).execute()
    response = await db.table("businesses").select("id").eq("slug", "intruder").execute()
    assert response.data == []


async def test_publishable_key_cannot_update_or_delete(
    public: AsyncClient, db: AsyncClient, seeded: dict[str, str]
) -> None:
    business_id = seeded["businesses"]
    for attempt in (
        public.table("businesses").update({"name": "Hijacked"}).eq("id", business_id),
        public.table("businesses").delete().eq("id", business_id),
    ):
        try:
            await attempt.execute()
        except APIError:
            pass  # refused outright (no grant); RLS alone would silently match no rows
    response = await db.table("businesses").select("name").eq("id", business_id).execute()
    assert response.data == [{"name": "Acme"}]
