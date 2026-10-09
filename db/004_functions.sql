-- Database functions the backend calls through the Supabase client (`rpc`): each one is a single transaction.
-- Paste into the Supabase SQL editor after 001-003 and run. Safe to run again.
-- Only the backend (secret key, `service_role`) may execute them; PUBLIC, anon and authenticated may not.

-- Insert (p_lead_id NULL) or update a lead, append its activities and, when p_analysis_trigger is set, enqueue its
-- AI analysis: all or nothing, so no lead is saved without its history (MAIN_PLAN §65).
-- p_values holds only the columns to write (column defaults apply to the rest); unknown keys fail.
CREATE OR REPLACE FUNCTION save_lead(
    p_business_id      uuid,
    p_lead_id          uuid,
    p_values           jsonb,
    p_activities       jsonb,
    p_analysis_trigger text DEFAULT NULL
) RETURNS leads
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_values  jsonb := p_values - 'id' - 'business_id';
    v_columns text;
    v_saved   leads;
BEGIN
    IF p_lead_id IS NULL THEN
        v_values := v_values || jsonb_build_object('business_id', p_business_id);
        SELECT string_agg(quote_ident(key), ', ') INTO v_columns FROM jsonb_object_keys(v_values) AS key;
        EXECUTE format(
            'INSERT INTO leads (%1$s) SELECT %1$s FROM jsonb_populate_record(NULL::leads, $1) RETURNING *', v_columns
        ) INTO v_saved USING v_values;
    ELSE
        v_values := v_values || jsonb_build_object('updated_at', now());
        SELECT string_agg(quote_ident(key), ', ') INTO v_columns FROM jsonb_object_keys(v_values) AS key;
        EXECUTE format(
            'UPDATE leads SET (%1$s) = (SELECT %1$s FROM jsonb_populate_record(NULL::leads, $1)) '
            'WHERE business_id = $2 AND id = $3 RETURNING *',
            v_columns
        ) INTO v_saved USING v_values, p_business_id, p_lead_id;
        IF v_saved.id IS NULL THEN
            RAISE EXCEPTION 'lead % not found', p_lead_id USING ERRCODE = 'P0002';
        END IF;
    END IF;

    -- One microsecond apart, so the timeline keeps the order the backend wrote them in.
    INSERT INTO activities (business_id, lead_id, activity_type, channel, description, metadata, created_at)
    SELECT p_business_id, v_saved.id, a.activity_type, a.channel, a.description, COALESCE(a.metadata, '{}'),
           now() + (a.ordinality * interval '1 microsecond')
    FROM ROWS FROM (
        jsonb_to_recordset(COALESCE(p_activities, '[]'))
            AS (activity_type text, channel text, description text, metadata jsonb)
    ) WITH ORDINALITY AS a(activity_type, channel, description, metadata, ordinality);

    IF p_analysis_trigger IS NOT NULL THEN
        PERFORM enqueue_analysis(p_business_id, v_saved.id, p_analysis_trigger);
    END IF;
    RETURN v_saved;
END;
$$;

-- The lead's open (pending or running) analysis job, created if there is none.
CREATE OR REPLACE FUNCTION enqueue_analysis(p_business_id uuid, p_lead_id uuid, p_trigger text)
RETURNS analysis_jobs
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_job analysis_jobs;
BEGIN
    INSERT INTO analysis_jobs (business_id, lead_id, trigger)
    VALUES (p_business_id, p_lead_id, p_trigger)
    ON CONFLICT (business_id, lead_id) WHERE status IN ('pending', 'running') DO NOTHING
    RETURNING * INTO v_job;
    IF v_job.id IS NULL THEN
        SELECT * INTO v_job FROM analysis_jobs
        WHERE business_id = p_business_id AND lead_id = p_lead_id AND status IN ('pending', 'running');
    END IF;
    RETURN v_job;
END;
$$;

-- Lease the next due job to p_worker: a pending job whose run_after has passed, or a running job whose worker
-- stopped renewing its lease (crashed). SKIP LOCKED lets many workers claim at once without taking the same job.
-- Returns no row when nothing is due.
CREATE OR REPLACE FUNCTION claim_analysis_job(p_worker text, p_lease_seconds integer)
RETURNS SETOF analysis_jobs
LANGUAGE sql
SET search_path = public
AS $$
    UPDATE analysis_jobs
    SET status = 'running',
        attempts = attempts + 1,
        worker = p_worker,
        locked_until = now() + make_interval(secs => p_lease_seconds),
        updated_at = now()
    WHERE id = (
        SELECT id FROM analysis_jobs
        WHERE (status = 'pending' AND run_after <= now()) OR (status = 'running' AND locked_until < now())
        ORDER BY run_after, created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;
$$;

-- Take (or renew) the business's write lease for p_ttl_seconds. True when p_holder now holds it; NULL when another
-- holder's lease has not expired yet.
CREATE OR REPLACE FUNCTION try_lock_business(p_business_id uuid, p_holder text, p_ttl_seconds integer)
RETURNS boolean
LANGUAGE sql
SET search_path = public
AS $$
    INSERT INTO business_locks (business_id, holder, expires_at)
    VALUES (p_business_id, p_holder, now() + make_interval(secs => p_ttl_seconds))
    ON CONFLICT (business_id) DO UPDATE
        SET holder = EXCLUDED.holder, expires_at = EXCLUDED.expires_at
        WHERE business_locks.expires_at < now() OR business_locks.holder = EXCLUDED.holder
    RETURNING true;
$$;

-- Functions are executable by PUBLIC by default; ALTER DEFAULT PRIVILEGES in 003 does not remove that.
REVOKE ALL ON FUNCTION save_lead(uuid, uuid, jsonb, jsonb, text)        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION enqueue_analysis(uuid, uuid, text)               FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION claim_analysis_job(text, integer)                FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION try_lock_business(uuid, text, integer)           FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION save_lead(uuid, uuid, jsonb, jsonb, text)     TO service_role;
GRANT EXECUTE ON FUNCTION enqueue_analysis(uuid, uuid, text)            TO service_role;
GRANT EXECUTE ON FUNCTION claim_analysis_job(text, integer)             TO service_role;
GRANT EXECUTE ON FUNCTION try_lock_business(uuid, text, integer)        TO service_role;
