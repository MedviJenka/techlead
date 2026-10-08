-- App users. `id` is the Supabase Auth user id (auth.users.id): Supabase Auth handles login and passwords,
-- this table holds the app-side profile, the user's business and role.
-- Paste into the Supabase SQL editor after 001 and run. Safe to run again.

CREATE TABLE IF NOT EXISTS users (
    id          UUID         NOT NULL,
    business_id UUID         NOT NULL,
    email       VARCHAR(320) NOT NULL,
    full_name   VARCHAR(200),
    role        VARCHAR(32)  NOT NULL DEFAULT 'sales',
    is_active   BOOLEAN      NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT pk_users PRIMARY KEY (id),
    CONSTRAINT fk_users_business_id_businesses FOREIGN KEY (business_id) REFERENCES businesses (id) ON DELETE CASCADE,
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT ck_users_user_role CHECK (role IN ('owner', 'manager', 'sales', 'admin'))
);

CREATE INDEX IF NOT EXISTS ix_users_business_id ON users (business_id);
