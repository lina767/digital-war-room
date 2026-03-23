-- Multi-tenancy: tenants, memberships, API keys; tenant_id on app tables; RLS on data tables.
-- Apply: psql $DATABASE_URL -f backend/migrations/003_multi_tenancy.sql
--
-- FastAPI sets per connection (via set_config):
--   app.active_tenant_id — UUID; RLS on embeddings / quality_signals / ais_track_samples
--   app.current_user_id  — optional (auditing / future policies)

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO tenants (id, name, slug)
VALUES (
    '00000000-0000-4000-8000-000000000001'::uuid,
    'Default',
    'default'
)
ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name;

CREATE TABLE IF NOT EXISTS tenant_memberships (
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id   UUID NOT NULL,
    role      TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_memberships_user ON tenant_memberships(user_id);

CREATE TABLE IF NOT EXISTS tenant_api_keys (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name        TEXT NOT NULL DEFAULT '',
    key_prefix  TEXT NOT NULL,
    key_hash    TEXT NOT NULL,
    scopes      JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at  TIMESTAMPTZ,
    UNIQUE (key_hash)
);

CREATE INDEX IF NOT EXISTS idx_tenant_api_keys_tenant ON tenant_api_keys(tenant_id) WHERE revoked_at IS NULL;

-- --- Alter existing tables (from 001 / 002) ---

ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
UPDATE embeddings SET tenant_id = '00000000-0000-4000-8000-000000000001'::uuid WHERE tenant_id IS NULL;
ALTER TABLE embeddings ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE embeddings ALTER COLUMN tenant_id SET DEFAULT '00000000-0000-4000-8000-000000000001'::uuid;

DROP INDEX IF EXISTS idx_embeddings_content_hash;
CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_tenant_content_hash ON embeddings (tenant_id, content_hash);

ALTER TABLE quality_signals ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
UPDATE quality_signals SET tenant_id = '00000000-0000-4000-8000-000000000001'::uuid WHERE tenant_id IS NULL;
ALTER TABLE quality_signals ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE quality_signals ALTER COLUMN tenant_id SET DEFAULT '00000000-0000-4000-8000-000000000001'::uuid;

ALTER TABLE quality_signals DROP CONSTRAINT IF EXISTS quality_signals_conflict_signal_key_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_quality_signals_tenant_conflict_key ON quality_signals (tenant_id, conflict, signal_key);

ALTER TABLE ais_track_samples ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
UPDATE ais_track_samples SET tenant_id = '00000000-0000-4000-8000-000000000001'::uuid WHERE tenant_id IS NULL;
ALTER TABLE ais_track_samples ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE ais_track_samples ALTER COLUMN tenant_id SET DEFAULT '00000000-0000-4000-8000-000000000001'::uuid;

DROP INDEX IF EXISTS idx_ais_track_mmsi_conflict_time;
CREATE INDEX IF NOT EXISTS idx_ais_track_tenant_mmsi_conflict_time
    ON ais_track_samples (tenant_id, mmsi, conflict, observed_at DESC);

-- --- RLS (data tables only; catalog tables enforced in FastAPI) ---
CREATE OR REPLACE FUNCTION public.app_active_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.active_tenant_id', true), '')::uuid;
$$;

CREATE OR REPLACE FUNCTION public.app_current_user_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid;
$$;

ALTER TABLE embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE quality_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE ais_track_samples ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS embeddings_tenant_isolation ON embeddings;
CREATE POLICY embeddings_tenant_isolation ON embeddings
    FOR ALL
    USING (tenant_id = public.app_active_tenant_id())
    WITH CHECK (tenant_id = public.app_active_tenant_id());

DROP POLICY IF EXISTS quality_signals_tenant_isolation ON quality_signals;
CREATE POLICY quality_signals_tenant_isolation ON quality_signals
    FOR ALL
    USING (tenant_id = public.app_active_tenant_id())
    WITH CHECK (tenant_id = public.app_active_tenant_id());

DROP POLICY IF EXISTS ais_track_tenant_isolation ON ais_track_samples;
CREATE POLICY ais_track_tenant_isolation ON ais_track_samples
    FOR ALL
    USING (tenant_id = public.app_active_tenant_id())
    WITH CHECK (tenant_id = public.app_active_tenant_id());
