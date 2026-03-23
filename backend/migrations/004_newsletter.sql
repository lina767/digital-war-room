-- Migration 004: Newsletter subscribers and daily-send deduplication lock (PostgreSQL)
-- Idempotent — safe to run multiple times.
--   psql $DATABASE_URL -f backend/migrations/004_newsletter.sql

CREATE TABLE IF NOT EXISTS newsletter_subscribers (
    id               BIGSERIAL PRIMARY KEY,
    email            TEXT        NOT NULL,
    conflict         TEXT        NOT NULL DEFAULT 'Global',
    subscribed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    unsubscribe_token TEXT       NOT NULL,
    confirm_token    TEXT        NOT NULL,
    confirmed_at     TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_newsletter_email
    ON newsletter_subscribers (email);

CREATE UNIQUE INDEX IF NOT EXISTS idx_newsletter_unsubscribe_token
    ON newsletter_subscribers (unsubscribe_token);

CREATE UNIQUE INDEX IF NOT EXISTS idx_newsletter_confirm_token
    ON newsletter_subscribers (confirm_token);

CREATE INDEX IF NOT EXISTS idx_newsletter_conflict
    ON newsletter_subscribers (conflict);

CREATE INDEX IF NOT EXISTS idx_newsletter_confirmed
    ON newsletter_subscribers (confirmed_at);

CREATE TABLE IF NOT EXISTS newsletter_daily_lock (
    day_utc      TEXT        PRIMARY KEY,
    started_at   TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ
);
