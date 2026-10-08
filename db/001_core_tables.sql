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
