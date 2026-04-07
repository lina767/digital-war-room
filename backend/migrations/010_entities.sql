-- Layer 2 cache foundation: normalized entities with stable UUIDs over time.
-- Vessel-first entity resolution (IMO, MMSI, canonical name) with tenant isolation.

CREATE TABLE IF NOT EXISTS entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                    DEFAULT '00000000-0000-4000-8000-000000000001'::uuid,
    entity_type     TEXT NOT NULL,
    canonical_name  TEXT NOT NULL,
    identifiers     JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entities_tenant_type_name
    ON entities (tenant_id, entity_type, canonical_name);

CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_tenant_type_imo
    ON entities (tenant_id, entity_type, (identifiers->>'imo'))
    WHERE (identifiers->>'imo') IS NOT NULL AND (identifiers->>'imo') <> '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_tenant_type_mmsi
    ON entities (tenant_id, entity_type, (identifiers->>'mmsi'))
    WHERE (identifiers->>'mmsi') IS NOT NULL AND (identifiers->>'mmsi') <> '';

ALTER TABLE entities ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS entities_tenant_isolation ON entities;
CREATE POLICY entities_tenant_isolation ON entities
    FOR ALL
    USING (tenant_id = public.app_active_tenant_id())
    WITH CHECK (tenant_id = public.app_active_tenant_id());
