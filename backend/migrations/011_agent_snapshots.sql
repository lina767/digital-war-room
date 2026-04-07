-- Layer 3 cache foundation: versioned per-agent snapshots linked to entities.

CREATE TABLE IF NOT EXISTS agent_snapshots (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name    TEXT NOT NULL,
    entity_id     UUID REFERENCES entities(id) ON DELETE SET NULL,
    run_id        UUID NOT NULL,
    conflict_key  TEXT NOT NULL,
    tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                  DEFAULT '00000000-0000-4000-8000-000000000001'::uuid,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    output        JSONB NOT NULL,
    confidence    DOUBLE PRECISION,
    sources       TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
    content_hash  TEXT NOT NULL,
    changed       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_agent_snapshots_lookup
    ON agent_snapshots (tenant_id, agent_name, conflict_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_snapshots_run
    ON agent_snapshots (run_id);

CREATE INDEX IF NOT EXISTS idx_agent_snapshots_entity
    ON agent_snapshots (entity_id, created_at DESC);

ALTER TABLE agent_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_snapshots_tenant_isolation ON agent_snapshots;
CREATE POLICY agent_snapshots_tenant_isolation ON agent_snapshots
    FOR ALL
    USING (tenant_id = public.app_active_tenant_id())
    WITH CHECK (tenant_id = public.app_active_tenant_id());
