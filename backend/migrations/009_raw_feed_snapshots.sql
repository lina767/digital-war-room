-- Layer 1 cache foundation: immutable, queryable raw feed snapshots.
-- Stores pre-filtered source responses + fetch metadata for reproducible reruns.

CREATE TABLE IF NOT EXISTS raw_feed_snapshots (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID REFERENCES tenants(id) ON DELETE SET NULL,
    source        TEXT NOT NULL,
    query_params  JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_payload   JSONB NOT NULL,
    content_hash  TEXT NOT NULL,
    conflict_key  TEXT,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_feed_snapshots_source_conflict_fetched
    ON raw_feed_snapshots (source, conflict_key, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_feed_snapshots_tenant_conflict_fetched
    ON raw_feed_snapshots (tenant_id, conflict_key, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_feed_snapshots_fetched_brin
    ON raw_feed_snapshots USING BRIN (fetched_at);
