-- Newsletter subscribers + daily lock (tenant-scoped). Apply after 003.
-- psql $DATABASE_URL -f backend/migrations/004_newsletter_postgres.sql

CREATE TABLE IF NOT EXISTS newsletter_subscribers (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE DEFAULT '00000000-0000-4000-8000-000000000001',
    email               TEXT NOT NULL,
    conflict            TEXT NOT NULL DEFAULT 'Global',
    subscribed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    unsubscribe_token   TEXT NOT NULL UNIQUE,
    confirm_token       TEXT NOT NULL UNIQUE,
    confirmed_at        TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_newsletter_tenant_email
    ON newsletter_subscribers (tenant_id, email);

CREATE INDEX IF NOT EXISTS idx_newsletter_tenant_conflict ON newsletter_subscribers (tenant_id, conflict);

CREATE TABLE IF NOT EXISTS newsletter_daily_lock (
    tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE DEFAULT '00000000-0000-4000-8000-000000000001',
    day_utc       TEXT NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL,
    completed_at  TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, day_utc)
);
