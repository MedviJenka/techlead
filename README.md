# techlead

AI lead-management platform. See `docs/plans/MAIN_PLAN.,md`.

## Layout

| Path | What |
|---|---|
| `app/` | FastAPI backend: `api/` (thin routes) → `services/` → `repositories/` → `models/` (SQLAlchemy) |
| `ai/` | CrewAI layer (crews, skills, guardrails, tools) |
| `migrations/` | Alembic migrations |
| `frontend/` | React + Vite + TanStack Query + React Router + Tailwind |

## Prerequisites

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Docker with Docker Compose >= 2.24 (`env_file` with `required: false`)
- Node 22 (only for running the frontend outside Docker)

Copy the example environment and fill in the blanks (`OPENAI_MODEL` is required):

```sh
cp .env.example .env
```

## Database

The app has one database: Supabase, via `SUPABASE_SQL_CONNECT_STRING` in `.env` (the `postgresql://...` connection
string, not `SUPABASE_PROJECT_URL`, which is the HTTPS REST endpoint). Set `DB_TRANSACTION_POOLER=true` only when
that string is the transaction-mode pooler (port 6543); run migrations over the direct or session-mode connection.

`alembic upgrade head` without `-x url=...` migrates **Supabase**. Alembic logs the target host before migrating.

The Docker `db` service is a local Postgres used **only by pytest** (`localhost:5433`, user/password `techlead`,
database `techlead_test`). It is not started by `docker compose up`.

## Run everything

```sh
docker compose up --build
```

- Frontend: http://localhost:5173
- API: http://localhost:8000/api/v1 (docs at http://localhost:8000/docs)

Ports are bound to `127.0.0.1` only. The backend container applies migrations to Supabase on start.

## Local development

```sh
uv sync
uv run alembic upgrade head          # migrates Supabase (SUPABASE_SQL_CONNECT_STRING)
uv run uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

## Checks

> **WARNING:** the platform tests run `alembic downgrade base` and `TRUNCATE` every table on `TEST_DATABASE_URL`
> (process environment variable; default `postgresql+asyncpg://techlead:techlead@localhost:5433/techlead_test`). Point it only at a disposable
> database whose name ends in `_test`, never at dev, shared or Supabase data (the fixture refuses Supabase hosts and
> names without `_test`).
>
> `techlead_test` is created by `docker/postgres-init` only when the `pgdata` volume is first initialised. If your
> volume predates that script: `docker compose exec db psql -U techlead -d techlead -c "CREATE DATABASE techlead_test OWNER techlead"`

```sh
docker compose up -d db              # local test Postgres
uv run pytest                        # platform tests skip if the test DB is unreachable
uv run ruff check app migrations tests/platform && uv run mypy
uv run alembic -x url=postgresql+asyncpg://techlead:techlead@localhost:5433/techlead_test check   # models vs migrations (local, after pytest)
cd frontend && npm run build && npm run lint
```

## New migration

`uv run alembic revision --autogenerate -m "..."`, then review the generated file.

Every new table must also be locked down for Supabase in its migration: `ALTER TABLE ... ENABLE ROW LEVEL
SECURITY` and revoke all grants from the `anon` and `authenticated` roles (guarded by a `pg_roles` check so it
still runs on plain PostgreSQL). Copy the pattern from
`migrations/versions/20261007_41144746c167_lock_down_supabase_data_api.py`.
