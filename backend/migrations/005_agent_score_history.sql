-- Daily agent scores for temporal / trend context (replaces SQLite file when using Postgres).
-- psql $DATABASE_URL -f backend/migrations/005_agent_score_history.sql

CREATE TABLE IF NOT EXISTS agent_daily_scores (
    conflict_key TEXT NOT NULL,
    agent_key    TEXT NOT NULL,
    day_utc      DATE NOT NULL,
    score        DOUBLE PRECISION NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (conflict_key, agent_key, day_utc)
);

CREATE INDEX IF NOT EXISTS idx_agent_daily_conflict_day ON agent_daily_scores (conflict_key, day_utc);
