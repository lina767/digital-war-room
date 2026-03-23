-- Cross-validation signals + AIS track history (PostgreSQL)
--   psql $DATABASE_URL -f backend/migrations/002_quality_signals_ais_tracks.sql

CREATE TABLE IF NOT EXISTS quality_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conflict        TEXT NOT NULL,
    signal_key      TEXT NOT NULL,
    canonical_text  TEXT NOT NULL,
    first_seen_utc  TIMESTAMPTZ NOT NULL,
    last_seen_utc   TIMESTAMPTZ NOT NULL,
    source_agents   JSONB NOT NULL DEFAULT '[]',
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    confidence      DOUBLE PRECISION NOT NULL DEFAULT 0,
    confirmation    TEXT NOT NULL DEFAULT 'unconfirmed',
    decay_state     TEXT NOT NULL DEFAULT 'active',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conflict, signal_key)
);

CREATE INDEX IF NOT EXISTS idx_quality_signals_conflict_decay
    ON quality_signals (conflict, decay_state);

CREATE INDEX IF NOT EXISTS idx_quality_signals_last_seen
    ON quality_signals (conflict, last_seen_utc DESC);

CREATE TABLE IF NOT EXISTS ais_track_samples (
    id              BIGSERIAL PRIMARY KEY,
    mmsi            TEXT NOT NULL,
    conflict        TEXT NOT NULL,
    observed_at     TIMESTAMPTZ NOT NULL,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ais_track_mmsi_conflict_time
    ON ais_track_samples (mmsi, conflict, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_ais_track_created
    ON ais_track_samples (created_at);
