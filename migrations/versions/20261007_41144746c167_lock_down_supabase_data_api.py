"""lock down supabase data api

Only the FastAPI backend may read or write these tables. On Supabase, the Data API (PostgREST) reaches the
`public` schema as `anon`/`authenticated`, so enable RLS with no policies (deny all) and revoke any grants those
roles received. The backend connects as the table owner, which bypasses RLS. On plain PostgreSQL (docker
compose) the Supabase roles do not exist and only the RLS flag is set.

Every new tenant table needs the same treatment in its own migration.

Revision ID: 41144746c167
Revises: dac288e936a6
Create Date: 2026-10-07 18:32:51.561900
"""

from collections.abc import Sequence

from alembic import op

revision: str = "41144746c167"
down_revision: str | None = "dac288e936a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("businesses", "leads", "activities")
SUPABASE_API_ROLES = ("anon", "authenticated")


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        for role in SUPABASE_API_ROLES:
            op.execute(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        REVOKE ALL ON TABLE {table} FROM {role};
                    END IF;
                END $$
                """
            )


def downgrade() -> None:
    # Revoked grants are not restored: these tables were never meant to be reachable through the Data API.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
