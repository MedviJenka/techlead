-- Only the FastAPI backend may read or write these tables. It uses the Supabase client with the secret key
-- (`service_role`, which bypasses RLS). The publishable key (`anon`/`authenticated`) gets nothing: RLS is on with
-- no policies (deny all) and their grants are revoked.
-- Paste into the Supabase SQL editor after the other files and run. Safe to run again.
-- Every new table must be added here.

ALTER TABLE businesses ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads      ENABLE ROW LEVEL SECURITY;
ALTER TABLE activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE users      ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE businesses, leads, activities, users FROM anon, authenticated;
GRANT ALL ON TABLE businesses, leads, activities, users TO service_role;

-- Tables created later in `public` start closed too.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES    FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;

-- Left over if an earlier Alembic-generated script was run; no longer used.
DROP TABLE IF EXISTS alembic_version;

-- Left over if an earlier db/004_functions.sql was run; the backend now does this work in Python.
DROP FUNCTION IF EXISTS save_lead(uuid, uuid, jsonb, jsonb);
DROP FUNCTION IF EXISTS dashboard_summary(uuid, jsonb);
