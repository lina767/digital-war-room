-- GreyNoise snapshot store (replaces SQLite greynoise_snapshots.db when using Postgres).
-- psql $DATABASE_URL -f backend/migrations/006_greynoise.sql

CREATE TABLE IF NOT EXISTS greynoise_snapshots (
    id               BIGSERIAL PRIMARY KEY,
    conflict         TEXT NOT NULL,
    snapshot_at      TIMESTAMPTZ NOT NULL,
    greynoise_score  DOUBLE PRECISION NOT NULL DEFAULT 0,
    absolute_score   DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_events     INTEGER NOT NULL DEFAULT 0,
    data_json        JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gn_conflict_ts ON greynoise_snapshots (conflict, snapshot_at DESC);

CREATE TABLE IF NOT EXISTS greynoise_ips (
    id                 BIGSERIAL PRIMARY KEY,
    conflict           TEXT NOT NULL,
    direction          TEXT NOT NULL,
    ip                 TEXT NOT NULL,
    classification     TEXT,
    tags_json          JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    snapshot_timestamp TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gn_ips_conflict_ts ON greynoise_ips (conflict, snapshot_timestamp DESC);

CREATE TABLE IF NOT EXISTS greynoise_pending_tags (
    id               BIGSERIAL PRIMARY KEY,
    tag_name         TEXT NOT NULL,
    conflict         TEXT NOT NULL,
    matched_category TEXT,
    discovered_at    TIMESTAMPTZ NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_gn_pending_tag_conflict ON greynoise_pending_tags (tag_name, conflict);
