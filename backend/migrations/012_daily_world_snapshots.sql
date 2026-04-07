-- Layer 5 cache foundation: one materialized world-state snapshot per conflict/day.

CREATE TABLE IF NOT EXISTS daily_world_snapshots (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conflict_key      TEXT NOT NULL,
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
                      DEFAULT '00000000-0000-4000-8000-000000000001'::uuid,
    snapshot_date     DATE NOT NULL,
    top_signals       JSONB NOT NULL DEFAULT '[]'::jsonb,
    chokepoint_status JSONB NOT NULL DEFAULT '[]'::jsonb,
    agent_scores      JSONB NOT NULL DEFAULT '{}'::jsonb,
    active_entities   JSONB NOT NULL DEFAULT '[]'::jsonb,
    diff_vs_prior     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conflict_key, tenant_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_world_snapshots_lookup
    ON daily_world_snapshots (tenant_id, conflict_key, snapshot_date DESC);

ALTER TABLE daily_world_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS daily_world_snapshots_tenant_isolation ON daily_world_snapshots;
CREATE POLICY daily_world_snapshots_tenant_isolation ON daily_world_snapshots
    FOR ALL
    USING (tenant_id = public.app_active_tenant_id())
    WITH CHECK (tenant_id = public.app_active_tenant_id());
