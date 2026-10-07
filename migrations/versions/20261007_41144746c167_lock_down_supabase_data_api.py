"""lock down supabase data api

Only the FastAPI backend may read or write these tables. On Supabase, the Data API (PostgREST) reaches the
`public` schema as `anon`/`authenticated`, so enable RLS with no policies (deny all) and revoke any grants those
roles received. That includes `alembic_version`: write access to it through the Data API would let anyone with
the publishable key make the next `alembic upgrade` skip or re-run migrations. The backend and Alembic connect
as the table owner, which bypasses RLS, so `alembic_version` stays fully usable for migrations.

The default privileges Supabase sets up in `public` (GRANT ALL ON TABLES/SEQUENCES/FUNCTIONS TO anon,
authenticated) are also revoked, so tables created later start closed. Limitation: default privileges are
per grantor role. This only covers objects later created by the role that runs this migration (the role in
SUPABASE_SQL_CONNECT_STRING, normally `postgres`); objects created by another role (e.g. `supabase_admin`) keep
that role's defaults. New tables should therefore still enable RLS in their own migration.

On plain PostgreSQL (docker compose) the Supabase roles do not exist and only the RLS flag is set.

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

TABLES = ("businesses", "leads", "activities", "alembic_version")
SUPABASE_API_ROLES = ("anon", "authenticated")
DEFAULT_PRIVILEGE_OBJECTS = ("TABLES", "SEQUENCES", "FUNCTIONS")


def _if_role_exists(role: str, statement: str) -> str:
    return f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                {statement};
            END IF;
        END $$
    """


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        for role in SUPABASE_API_ROLES:
            op.execute(_if_role_exists(role, f"REVOKE ALL ON TABLE {table} FROM {role}"))
    for role in SUPABASE_API_ROLES:
        for objects in DEFAULT_PRIVILEGE_OBJECTS:
            op.execute(
                _if_role_exists(role, f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON {objects} FROM {role}")
            )


def downgrade() -> None:
    # Revoked grants and default privileges are not restored: these tables were never meant to be reachable
    # through the Data API.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
