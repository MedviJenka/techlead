-- Auto-send: a first reply the owner has not decided on within the business's timeout is sent by the worker.
-- For databases created before it; db/001_core_tables.sql already has all of this. Safe to run again.

ALTER TABLE whatsapp_accounts ADD COLUMN IF NOT EXISTS auto_send_after_minutes INTEGER;
ALTER TABLE whatsapp_accounts DROP CONSTRAINT IF EXISTS ck_whatsapp_accounts_auto_send_after_minutes;
ALTER TABLE whatsapp_accounts ADD CONSTRAINT ck_whatsapp_accounts_auto_send_after_minutes
    CHECK (auto_send_after_minutes BETWEEN 1 AND 1440);

ALTER TABLE reply_drafts ADD COLUMN IF NOT EXISTS auto_send_at TIMESTAMPTZ;
ALTER TABLE reply_drafts DROP CONSTRAINT IF EXISTS ck_reply_drafts_decision_channel;
ALTER TABLE reply_drafts ADD CONSTRAINT ck_reply_drafts_decision_channel
    CHECK (decided_via IN ('whatsapp', 'dashboard', 'auto'));

CREATE INDEX IF NOT EXISTS ix_reply_drafts_auto_send_at
    ON reply_drafts (auto_send_at) WHERE status = 'pending_approval' AND auto_send_at IS NOT NULL;
