-- Migration 001: Enable pgvector and create embeddings table
-- Run against your Railway PostgreSQL instance:
--   psql $DATABASE_URL -f backend/migrations/001_pgvector_setup.sql
--
-- Prerequisites: PostgreSQL 15+ with pgvector extension available
-- (Railway Postgres includes pgvector by default)

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS embeddings (
    id          BIGSERIAL PRIMARY KEY,
    content_hash TEXT        NOT NULL,
    source      TEXT        NOT NULL DEFAULT 'unknown',
    text_preview TEXT,
    embedding   vector(384) NOT NULL,
    metadata    JSONB       DEFAULT '{}',
    conflict    TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_content_hash
    ON embeddings (content_hash);

CREATE INDEX IF NOT EXISTS idx_embeddings_source
    ON embeddings (source);

CREATE INDEX IF NOT EXISTS idx_embeddings_conflict
    ON embeddings (conflict);

-- IVFFlat index for approximate nearest-neighbor search.
-- Requires at least ~1000 rows to be effective; until then Postgres
-- falls back to exact sequential scan which is fine for small datasets.
-- lists = sqrt(expected_row_count); 100 is a reasonable starting point.
CREATE INDEX IF NOT EXISTS idx_embeddings_vector_ivfflat
    ON embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Function to auto-update updated_at on row modification
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_updated_at ON embeddings;
CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON embeddings
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();
