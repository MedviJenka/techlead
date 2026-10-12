-- Core tables: businesses (tenants), leads, activities.
-- Paste into the Supabase SQL editor and run. Safe to run again: existing tables are left as they are.
-- The SQLAlchemy models in app/models/ must match these tables; change both together.

CREATE TABLE IF NOT EXISTS businesses (
    id                       UUID         NOT NULL DEFAULT gen_random_uuid(),
    name                     VARCHAR(200) NOT NULL,
    slug                     VARCHAR(100) NOT NULL,
    industry                 VARCHAR(100),
    timezone                 VARCHAR(64)  NOT NULL DEFAULT 'UTC',
    configuration            JSONB        NOT NULL DEFAULT '{}',
    custom_field_definitions JSONB        NOT NULL DEFAULT '[]',
    ai_configuration         JSONB        NOT NULL DEFAULT '{}',
    created_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT pk_businesses PRIMARY KEY (id),
    CONSTRAINT uq_businesses_slug UNIQUE (slug)
);

CREATE TABLE IF NOT EXISTS leads (
    id                 UUID         NOT NULL DEFAULT gen_random_uuid(),
    business_id        UUID         NOT NULL,
    external_id        VARCHAR(255),
    source             VARCHAR(50)  NOT NULL,
    status             VARCHAR(50)  NOT NULL DEFAULT 'new',
    priority           VARCHAR(32),
    first_name         VARCHAR(100),
    last_name          VARCHAR(100),
    email              VARCHAR(320),
    phone              VARCHAR(32),
    company_name       VARCHAR(200),
    notes              TEXT,
    lead_score         INTEGER,
    sentiment          VARCHAR(32),
    ai_summary         TEXT,
    recommended_action VARCHAR(50),
    custom_fields      JSONB        NOT NULL DEFAULT '{}',
    raw_payload        JSONB        NOT NULL DEFAULT '{}',
    last_contact_at    TIMESTAMPTZ,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT pk_leads PRIMARY KEY (id),
    CONSTRAINT fk_leads_business_id_businesses FOREIGN KEY (business_id) REFERENCES businesses (id) ON DELETE CASCADE,
    CONSTRAINT uq_leads_business_id_id UNIQUE (business_id, id),
    CONSTRAINT ck_leads_lead_score_range CHECK (lead_score BETWEEN 0 AND 100),
    CONSTRAINT ck_leads_lead_priority CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT ck_leads_lead_sentiment CHECK (sentiment IN ('negative', 'neutral', 'mixed', 'positive'))
);

CREATE INDEX IF NOT EXISTS ix_leads_business_id_created_at ON leads (business_id, created_at);
CREATE INDEX IF NOT EXISTS ix_leads_business_id_email ON leads (business_id, email);
CREATE INDEX IF NOT EXISTS ix_leads_business_id_phone ON leads (business_id, phone);
CREATE INDEX IF NOT EXISTS ix_leads_business_id_status ON leads (business_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_business_id_source_external_id
    ON leads (business_id, source, external_id) WHERE external_id IS NOT NULL;

-- Append-only lead history.
CREATE TABLE IF NOT EXISTS activities (
    id            UUID        NOT NULL DEFAULT gen_random_uuid(),
    business_id   UUID        NOT NULL,
    lead_id       UUID        NOT NULL,
    activity_type VARCHAR(32) NOT NULL,
    channel       VARCHAR(32),
    description   TEXT        NOT NULL,
    metadata      JSONB       NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_activities PRIMARY KEY (id),
    CONSTRAINT fk_activities_business_id_businesses FOREIGN KEY (business_id) REFERENCES businesses (id) ON DELETE CASCADE,
    CONSTRAINT fk_activities_business_id_lead_id_leads
        FOREIGN KEY (business_id, lead_id) REFERENCES leads (business_id, id) ON DELETE CASCADE,
    CONSTRAINT ck_activities_activity_type CHECK (activity_type IN (
        'lead_created', 'lead_updated', 'email_sent', 'email_received', 'whatsapp_sent', 'whatsapp_received',
        'phone_call', 'status_changed', 'score_changed', 'proposal_sent', 'meeting_scheduled', 'ai_analysis',
        'followup_created'
    )),
    CONSTRAINT ck_activities_activity_channel CHECK (channel IN ('whatsapp', 'email', 'sms', 'phone', 'crm_task'))
);

CREATE INDEX IF NOT EXISTS ix_activities_business_id_lead_id_created_at ON activities (business_id, lead_id, created_at);

-- AI analysis jobs (MAIN_PLAN §58, §65). A saved lead or POST /analyze enqueues one; the worker (app/worker)
-- claims it with claim_analysis_job (db/004_functions.sql), runs NewLeadFlow and records the outcome and cost.
CREATE TABLE IF NOT EXISTS analysis_jobs (
    id           UUID           NOT NULL DEFAULT gen_random_uuid(),
    business_id  UUID           NOT NULL,
    lead_id      UUID           NOT NULL,
    trigger      VARCHAR(32)    NOT NULL,
    status       VARCHAR(32)    NOT NULL DEFAULT 'pending',
    attempts     INTEGER        NOT NULL DEFAULT 0,
    max_attempts INTEGER        NOT NULL DEFAULT 5,
    run_after    TIMESTAMPTZ    NOT NULL DEFAULT now(),
    locked_until TIMESTAMPTZ,
    worker       VARCHAR(200),
    last_error   TEXT,
    usage        JSONB,
    cost_usd     NUMERIC(12, 6),
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ    NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    CONSTRAINT pk_analysis_jobs PRIMARY KEY (id),
    CONSTRAINT fk_analysis_jobs_business_id_businesses
        FOREIGN KEY (business_id) REFERENCES businesses (id) ON DELETE CASCADE,
    CONSTRAINT fk_analysis_jobs_business_id_lead_id_leads
        FOREIGN KEY (business_id, lead_id) REFERENCES leads (business_id, id) ON DELETE CASCADE,
    CONSTRAINT ck_analysis_jobs_analysis_job_status CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    CONSTRAINT ck_analysis_jobs_analysis_trigger CHECK (trigger IN ('lead_created', 'manual'))
);

-- At most one open job per lead: enqueueing again while one is pending or running returns that job.
CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_jobs_open_lead
    ON analysis_jobs (business_id, lead_id) WHERE status IN ('pending', 'running');
CREATE INDEX IF NOT EXISTS ix_analysis_jobs_pending_run_after ON analysis_jobs (run_after) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS ix_analysis_jobs_running_locked_until
    ON analysis_jobs (locked_until) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS ix_analysis_jobs_business_id_lead_id_created_at
    ON analysis_jobs (business_id, lead_id, created_at);

-- Per-business write lease, shared by every backend and worker process (try_lock_business in db/004_functions.sql).
-- It serializes match-then-save deduplication across processes; an expired lease may be taken over.
CREATE TABLE IF NOT EXISTS business_locks (
    business_id UUID         NOT NULL,
    holder      VARCHAR(200) NOT NULL,
    expires_at  TIMESTAMPTZ  NOT NULL,
    CONSTRAINT pk_business_locks PRIMARY KEY (business_id),
    CONSTRAINT fk_business_locks_business_id_businesses
        FOREIGN KEY (business_id) REFERENCES businesses (id) ON DELETE CASCADE
);

-- A business's WhatsApp Business number (MAIN_PLAN §66). Inbound webhooks name the Meta `phone_number_id`, which
-- maps the event to its business. Messages from `owner_phone` (E.164) are the owner's approval decisions.
CREATE TABLE IF NOT EXISTS whatsapp_accounts (
    business_id     UUID        NOT NULL,
    phone_number_id VARCHAR(64) NOT NULL,
    display_phone   VARCHAR(32),
    owner_phone     VARCHAR(32) NOT NULL,
    auto_send_after_minutes INTEGER,  -- an undecided first reply is sent after this long; NULL: never
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_whatsapp_accounts PRIMARY KEY (business_id),
    CONSTRAINT ck_whatsapp_accounts_auto_send_after_minutes CHECK (auto_send_after_minutes BETWEEN 1 AND 1440),
    CONSTRAINT fk_whatsapp_accounts_business_id_businesses
        FOREIGN KEY (business_id) REFERENCES businesses (id) ON DELETE CASCADE,
    CONSTRAINT uq_whatsapp_accounts_phone_number_id UNIQUE (phone_number_id)
);

-- Every inbound webhook event, recorded before it is processed (MAIN_PLAN §59): a redelivered event is processed
-- once. claim_ingest_event (db/004_functions.sql) inserts it or hands back a failed (or stuck) one for a retry.
CREATE TABLE IF NOT EXISTS ingest_events (
    id                UUID         NOT NULL DEFAULT gen_random_uuid(),
    business_id       UUID         NOT NULL,
    source            VARCHAR(32)  NOT NULL,
    external_event_id VARCHAR(255) NOT NULL,
    event_type        VARCHAR(32)  NOT NULL,
    status            VARCHAR(32)  NOT NULL DEFAULT 'processing',
    attempts          INTEGER      NOT NULL DEFAULT 1,
    payload           JSONB        NOT NULL DEFAULT '{}',
    last_error        TEXT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    processed_at      TIMESTAMPTZ,
    CONSTRAINT pk_ingest_events PRIMARY KEY (id),
    CONSTRAINT fk_ingest_events_business_id_businesses
        FOREIGN KEY (business_id) REFERENCES businesses (id) ON DELETE CASCADE,
    CONSTRAINT uq_ingest_events_business_id_source_external_event_id UNIQUE (business_id, source, external_event_id),
    CONSTRAINT ck_ingest_events_ingest_status CHECK (status IN ('processing', 'processed', 'ignored', 'failed'))
);

-- AI-drafted replies awaiting the owner (MAIN_PLAN §42, §66): Approve sends it, Edit sends the owner's text instead,
-- Reject drops it. `approval_message_id` is the approval request sent to the owner on WhatsApp.
CREATE TABLE IF NOT EXISTS reply_drafts (
    id                  UUID         NOT NULL DEFAULT gen_random_uuid(),
    business_id         UUID         NOT NULL,
    lead_id             UUID         NOT NULL,
    channel             VARCHAR(32)  NOT NULL,
    message             TEXT         NOT NULL,
    objective           TEXT,
    status              VARCHAR(32)  NOT NULL DEFAULT 'pending_approval',
    edited              BOOLEAN      NOT NULL DEFAULT false,
    decided_via         VARCHAR(32),
    approval_message_id VARCHAR(255),
    sent_message_id     VARCHAR(255),
    last_error          TEXT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    decided_at          TIMESTAMPTZ,
    sent_at             TIMESTAMPTZ,
    auto_send_at        TIMESTAMPTZ,  -- sent by the worker then if still pending_approval; NULL: never
    CONSTRAINT pk_reply_drafts PRIMARY KEY (id),
    CONSTRAINT fk_reply_drafts_business_id_businesses
        FOREIGN KEY (business_id) REFERENCES businesses (id) ON DELETE CASCADE,
    CONSTRAINT fk_reply_drafts_business_id_lead_id_leads
        FOREIGN KEY (business_id, lead_id) REFERENCES leads (business_id, id) ON DELETE CASCADE,
    CONSTRAINT ck_reply_drafts_reply_draft_status CHECK (status IN (
        'pending_approval', 'awaiting_edit', 'sending', 'sent', 'rejected', 'failed'
    )),
    CONSTRAINT ck_reply_drafts_reply_channel CHECK (channel IN ('whatsapp', 'email', 'sms', 'phone', 'crm_task')),
    CONSTRAINT ck_reply_drafts_decision_channel CHECK (decided_via IN ('whatsapp', 'dashboard', 'auto'))
);

-- At most one undecided draft per lead.
CREATE UNIQUE INDEX IF NOT EXISTS uq_reply_drafts_open_lead
    ON reply_drafts (business_id, lead_id) WHERE status IN ('pending_approval', 'awaiting_edit', 'sending');
CREATE INDEX IF NOT EXISTS ix_reply_drafts_business_id_status_created_at
    ON reply_drafts (business_id, status, created_at);
-- The worker's auto-send sweep, across businesses.
CREATE INDEX IF NOT EXISTS ix_reply_drafts_auto_send_at
    ON reply_drafts (auto_send_at) WHERE status = 'pending_approval' AND auto_send_at IS NOT NULL;
