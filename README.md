# techlead

AI lead-management platform. See `docs/plans/MAIN_PLAN.,md`.

## Layout

| Path | What |
|---|---|
| `app/` | FastAPI backend: `api/` (thin routes) → `services/` → `repositories/` (Supabase client) → `models/` (typed rows) |
| `ai/` | CrewAI layer (crews, skills, guardrails, tools) |
| `db/` | The database schema: SQL files to paste into the Supabase SQL editor |
| `frontend/` | React + Vite + TanStack Query + React Router + Tailwind |

## Prerequisites

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- A Supabase project (the only database; nothing runs locally)
- Docker with Docker Compose >= 2.24 (`env_file` with `required: false`)
- Node 22 (only for running the frontend outside Docker)

Copy the example environment and fill in the blanks (`OPENAI_MODEL` is required):

```sh
cp .env.example .env
```

## Database

The app has one database: Supabase. Every database call goes through the Supabase Python client
(`app/core/supabase.py`), using `SUPABASE_PROJECT_URL` and `SUPABASE_SECRET_KEY` from `.env`.

Create the tables by pasting the files in `db/` into the Supabase SQL editor, in numeric order:

| File | What |
|---|---|
| `001_core_tables.sql` | `businesses`, `leads`, `activities`, `analysis_jobs`, `business_locks`, `whatsapp_accounts`, `ingest_events`, `reply_drafts` |
| `002_users.sql` | `users` (app profile; `id` is the Supabase Auth user id) |
| `003_lock_down_data_api.sql` | RLS on, publishable key gets no access, secret key (`service_role`) gets full access |
| `004_functions.sql` | `save_lead` (lead + activities + job in one transaction), the AI job queue, the per-business lock, `claim_ingest_event` (webhook idempotency) |

Every file is safe to run again. To change the schema, edit or add a file in `db/`, run it in the SQL editor, and
update the matching row model in `app/models/`. A new table also goes into `003_lock_down_data_api.sql`.
`tests/platform/test_enum_check_drift.py` checks (without a database) that the SQL and the models agree.

## Sign in with Google

Users sign in with Google through Supabase Auth in the browser (`frontend/src/auth/supabase.ts`). The frontend sends
the session's access token to the API, and the backend verifies it against the project's public keys
(`app/core/auth.py`). Every API route except `/health` requires it.

One-time setup:

- Google Cloud: a **Web application** OAuth client whose authorized redirect URI is the Supabase callback
  (`https://<project-ref>.supabase.co/auth/v1/callback`).
- Supabase > Authentication > Providers > Google: enabled, with that client ID and secret. They are not needed in `.env`.
- Supabase > Authentication > URL Configuration: Site URL `http://localhost:5173`, and add `http://localhost:5173/**`
  to the redirect URLs.
- `.env`: `SUPABASE_PROJECT_URL` and `SUPABASE_PUBLISHABLE_KEY`. The frontend reads only these two.

## Run everything

```sh
docker compose up --build
```

- Frontend: http://localhost:5173
- API: http://localhost:8000/api/v1 (docs at http://localhost:8000/docs)

Ports are bound to `127.0.0.1` only.

## Local development

```sh
uv sync
uv run uvicorn app.main:app --reload
uv run python -m app.worker          # AI worker: runs queued analyses (real LLM calls)
cd frontend && npm install && npm run dev
```

## Checks

> **WARNING:** the platform tests delete every row in the project given by `TEST_SUPABASE_URL` /
> `TEST_SUPABASE_SECRET_KEY` (in `.env`). Use a **separate Supabase project** just for tests and paste `db/*.sql`
> into its SQL editor too. The fixture refuses the app's own project (`SUPABASE_PROJECT_URL`).

```sh
uv run pytest                        # database tests skip if the test project is not configured
uv run ruff check app tests/platform && uv run mypy
cd frontend && npm run build && npm run lint
```

`tests/platform/test_data_api_lockdown.py` checks that the publishable key cannot read or write any table: always
against `db/003_lock_down_data_api.sql`, and live against the test project when `TEST_SUPABASE_PUBLISHABLE_KEY` is set.

CI (`.github/workflows/ci.yml`) runs the same checks plus `docker compose build` on every pull request and on pushes
to `main` and `integration`. The database tests run there only when the repository secrets `TEST_SUPABASE_URL`,
`TEST_SUPABASE_SECRET_KEY` and `TEST_SUPABASE_PUBLISHABLE_KEY` point at the separate test project.

## Phase 2: lead management

Open a business to see its dashboard, then choose **View & import leads** and select
`docs/files/sample_raw_leads.json`. The import result reports created, updated, skipped, and failed records,
with validation errors for each failed record. The lead table supports search, status/source/priority filters,
and pagination. Open a lead to edit its status, priority, and notes or inspect its activity history.

Business-scoped API routes under `/api/v1/businesses/{business_id}`:

| Method | Route | Purpose |
|---|---|---|
| GET / POST | `/leads` | Paginated search / normalized create-or-merge |
| POST | `/leads/import` | Import a sample-shaped JSON envelope (up to 1,000 records) |
| GET / PATCH | `/leads/{lead_id}` | Lead details / partial update |
| GET | `/leads/{lead_id}/activities` | Chronological, paginated activity history |
| GET | `/dashboard` | Counts, distributions, top open leads, recent activity |

Deduplication matches within the business, in order: source + external ID, normalized email, normalized phone.
Contact matches use the oldest matching lead. Non-null incoming fields overwrite existing values; custom fields
are merged by key. The original source, external ID, and creation time remain unchanged on merges. Explicit
PATCH requests can clear nullable fields and replace custom fields. Identical replays add no activities.
Raw source payloads are retained in storage but never returned by these APIs. Imported engagement facts are
recorded on the creation event, without inventing individual messages or calls.

Lead writes for one business are serialized by an in-process lock (`app/services/lead.py`), preventing races
between imports and manual writes; separate businesses can write concurrently. The lock only spans one backend
process, so run a single process. A lead is saved first and its activities right after
(two requests, not one transaction); an import saves record by record, so a record that fails validation or a constraint is reported and the rest are
kept.

Dashboard: hot means high/critical priority; closed statuses and follow-up timing come from the business settings
(Phase 3). Inactive includes `unresponsive` leads and open leads with no contact for seven days since creation. The
proposal card counts `proposal_sent` leads. These endpoints do not call an LLM. Each signed-in user belongs to one business (a `users`
row): creating a business makes you its owner, and every other business answers 404. Inviting more users to a
business is not built yet.

## Phase 3: deterministic intelligence

Open **Settings** to configure, per business, everything below; **Save and rescore leads** applies the new rules to
every stored lead. A business that never saved settings uses the defaults. The settings live in the existing
`businesses.configuration` and `businesses.custom_field_definitions` JSONB columns (no schema change).

- **Scoring rules** (MAIN_PLAN §48). Every lead starts at a base score (default 40); each rule whose conditions
  all hold adds its points (negative to subtract), clamped to 0-100. Rules test named lead facts built from the
  lead row and its activity history (`app/intelligence/facts.py`): `budget_known`, `timeframe_days`, `replied`,
  `contact_attempts`, `ignored_follow_ups`, `days_since_last_contact`, `proposal_sent`, `status`, `notes`, ... or
  any `custom_fields.<key>`. Budget and timeframe come from the `budget` and `timeframe` custom fields; the
  import copies them there from a record's `intent` section. The defaults are the plan's example rules.
- **AI blend.** When a lead has an AI score it is blended in: `rules * (1 - ai_weight) + ai * ai_weight`
  (default weight 0.4). Until the CrewAI phases, the only AI score is the one an import brings
  (`ai.lead_score`, kept in the raw payload).
- **Priority** follows the score through thresholds (defaults: critical 95, high 80, medium 50, else low). A
  priority set explicitly (in the editor, the API, or by the import source) is kept until the score changes.
- **Follow-up**: when the next contact is due, computed on read and returned on every lead (`follow_up`). Never
  contacted: a first-response window per priority from creation; contacted: an interval per priority (or per
  status, e.g. `proposal_sent`) from the last contact. Closed statuses need no follow-up. The dashboard's
  "Needs follow-up" counts overdue open leads.
- **Custom fields** (MAIN_PLAN §53): typed definitions (`text`, `number`, `boolean`, `date`, `select`). Lead
  custom fields are checked against them on create, update and import (422 / a failed import record); keys
  without a definition are kept as they arrive.

The score is stored on every lead write with a `score_changed` activity holding the matched rules, so score
history explains itself. Time-based rules (days since contact) move only on the next write or rescore;
`GET /leads/{lead_id}/score` always shows the live breakdown.

| Method | Route | Purpose |
|---|---|---|
| PUT | `/businesses/{business_id}/settings` | Replace configuration and custom field definitions |
| POST | `/businesses/{business_id}/leads/rescore` | Recompute every lead's score and priority |
| GET | `/businesses/{business_id}/leads/{lead_id}/score` | Live score breakdown (matched rules, AI blend) |

## AI analysis (NewLeadFlow, background worker)

AI never runs inside an API request. Saving a **new** lead (create or import) queues an analysis job in the same
database transaction; **Analyze with AI** on a lead page queues one too:
`POST /businesses/{business_id}/leads/{lead_id}/analyze` answers `202` with the job at once. The frontend polls
`GET .../leads/{lead_id}/analysis` (the latest job and the latest saved result) until the job finishes.

The worker (`python -m app.worker`, the `worker` Compose service) claims due jobs and runs `NewLeadFlow`
(`app/analysis/flow.py`): the `LeadIntelligenceCrew` (qualification, AI scoring, next action), then the deterministic
score, the blended final score and priority, and a priority route (hot / warm / cold).

- **Cost**: each run makes several real LLM calls with `OPENAI_MODEL` / `AI_REASONING_MODEL`. Every new lead is
  analysed unless the business sets `ai_configuration.auto_analyze` to `false`. Token counts are stored on the job and
  in the `ai_analysis` activity; set `AI_PRICE_INPUT_PER_MTOK` and `AI_PRICE_OUTPUT_PER_MTOK` to also store dollars.
- **Images**: the API image has no CrewAI (`uv sync --no-default-groups`); the worker image adds the `ai` dependency
  group. Run as many workers as you like: jobs are claimed with `FOR UPDATE SKIP LOCKED`.
- **Failures**: a failed run is retried with exponential backoff (30 s doubling, up to 5 attempts) and never changes
  the lead. A worker that dies mid-run leaves its job leased; another worker takes it over when the lease expires.
  The worker refuses to start without `OPENAI_API_KEY` (for OpenAI models).
- **Isolation**: the crew's tools read a snapshot of that one lead, its activities and its business
  (`app/analysis/read_service.py`), loaded before the crew starts. An agent cannot reach another lead or tenant.
- **What is saved**: the qualification summary (`ai_summary`), the recommended action (`recommended_action`) and an
  `ai_analysis` activity holding the full result and its cost. Its AI score replaces the imported one in the score
  blend from then on; the priority stays rule-based (the AI's own priority is advice only).
- **Concurrency**: lead writes take a per-business lease in the database (`business_locks`), so any number of API
  and worker processes can write safely; a lead and its activities are saved in one transaction (`save_lead`).

Run it once by hand with `python -m ai.crews.lead_intelligence lead_008` (sample data, real LLM calls).

## WhatsApp: first reply within a minute (Phase 7)

A lead writes to the business's WhatsApp number; within a minute the owner gets an AI-drafted reply on their own
WhatsApp with **Approve / Edit / Reject**. Nothing reaches a lead until the owner approves it.

```text
lead writes on WhatsApp ──> POST /api/v1/webhooks/whatsapp (signature checked, ingest_events: once per message)
   └─> lead created or joined by phone (E.164) + whatsapp_received activity + analysis job, in one transaction
worker: NewLeadFlow ──> LeadIntelligenceCrew, score, priority route ──> ConversationCrew drafts the first reply
   └─> reply_drafts row ──> owner's WhatsApp: "New lead … Suggested reply …" [Approve] [Edit] [Reject]
owner taps Approve ──> reply sent to the lead, whatsapp_sent activity (the lead counts as answered)
owner taps Edit ──> "Send me the reply as you want it" ──> their next message is sent instead
```

Setup (once per deployment, in a Meta developer app with the WhatsApp product):

1. In `.env`: `WHATSAPP_ACCESS_TOKEN` (a system-user token with `whatsapp_business_messaging`),
   `WHATSAPP_APP_SECRET` (App settings > Basic) and `WHATSAPP_VERIFY_TOKEN` (any secret string).
2. In the Meta app's WhatsApp webhook settings: callback URL `https://<your host>/api/v1/webhooks/whatsapp`, the
   same verify token, and subscribe to the `messages` field.
3. Each business: **Settings > WhatsApp**: the number's *Phone number ID* and the owner's own WhatsApp number.
   Set **Country code for phone numbers** too, so local numbers (`050-…`) match WhatsApp's international ones.

- **Owner outside the 24-hour window**: WhatsApp only delivers free-form messages to people who wrote in the last
  24 hours. Create an approved template (body `{{1}}` lead name, `{{2}}` suggested reply, three quick-reply buttons:
  Approve, Edit, Reject) and set `WHATSAPP_APPROVAL_TEMPLATE`; without one, such drafts wait on the dashboard.
- **Dashboard fallback**: the dashboard lists replies waiting for a decision (approve, edit, reject there too) and
  shows the median time to first response and the open leads nobody has answered.
- **Idempotency**: every inbound message is claimed in `ingest_events` before it is processed. A redelivered webhook
  changes nothing; a message that failed answers `500`, so Meta redelivers it and only it is processed again.
- **Decisions**: one draft per lead is open at a time, and approving, editing or rejecting is a conditional update:
  a double tap, or the phone and the dashboard at once, send at most one reply.
- **Industry preset**: choosing *Real estate* when creating a business starts it with real-estate lead fields (area,
  rooms, budget, financing, move-in timing...), scoring rules, fast follow-up timing and AI instructions
  (`app/presets.py`, `GET /api/v1/businesses/presets`). Everything stays editable in Settings.

