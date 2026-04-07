-- Chat MVP: authoritative storage for each /api/chat/ask reply (feedback links by response_id).
-- Apply: psql $DATABASE_URL -f backend/migrations/008_chat_responses.sql

CREATE TABLE IF NOT EXISTS chat_responses (
    response_id       UUID PRIMARY KEY,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id         UUID NULL,
    conflict          TEXT NOT NULL,
    question_type     TEXT NOT NULL,
    question          TEXT NOT NULL,
    answer            TEXT NOT NULL,
    confidence_score  DOUBLE PRECISION NOT NULL,
    sources_json      JSONB NOT NULL DEFAULT '[]'::jsonb,
    fallback_used     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_chat_responses_tenant_created
    ON chat_responses (tenant_id, created_at DESC);
