-- ============================================================
-- Phase 14: Pipeline Integrity — Embedding Registry, Dead Letter Queue, Metrics, State Machine
-- Sheppard v1.3.0-phase14
--
-- Adds:
-- 1. audit.embedding_registry — tracks embedding model/version per source
-- 2. audit.dead_letter_queue — structured failure tracking with replay
-- 3. audit.pipeline_metrics — queryable analytics table
-- 4. CHECK constraint on corpus.sources.status (valid states only)
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. Embedding Registry
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit.embedding_registry (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           TEXT NOT NULL REFERENCES corpus.sources(source_id) ON DELETE CASCADE,
    content_hash        TEXT NOT NULL,
    embedding_model     TEXT NOT NULL,
    embedding_version   TEXT NOT NULL DEFAULT 'v1',
    embed_host          TEXT NOT NULL,
    embed_dim           INT NOT NULL,
    chroma_doc_id       TEXT NOT NULL,
    chroma_collection   TEXT NOT NULL DEFAULT 'knowledge_atoms',
    status              TEXT NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_embedding_registry_source
    ON audit.embedding_registry(source_id);
CREATE INDEX IF NOT EXISTS idx_embedding_registry_model
    ON audit.embedding_registry(embedding_model, embedding_version);
CREATE INDEX IF NOT EXISTS idx_embedding_registry_stale
    ON audit.embedding_registry(status) WHERE status != 'active';

COMMENT ON TABLE audit.embedding_registry IS
    'Tracks which embedding model/version produced which vectors. Source of truth for rebuild decisions. NOT stored in Chroma metadata.';

-- ────────────────────────────────────────────────────────────
-- 2. Dead Letter Queue
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit.dead_letter_queue (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           TEXT,
    stage               TEXT NOT NULL,
    error_class         TEXT NOT NULL,
    error_detail        TEXT,
    retry_count         INT NOT NULL DEFAULT 0,
    max_retries         INT NOT NULL DEFAULT 3,
    last_seen_worker    TEXT,
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              TEXT NOT NULL DEFAULT 'pending',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dlq_status ON audit.dead_letter_queue(status);
CREATE INDEX IF NOT EXISTS idx_dlq_stage ON audit.dead_letter_queue(stage);
CREATE INDEX IF NOT EXISTS idx_dlq_created ON audit.dead_letter_queue(created_at DESC) WHERE status = 'pending';

COMMENT ON TABLE audit.dead_letter_queue IS
    'Structured dead-letter store for pipeline failures. Supports replay via payload JSONB. Manual inspection required.';

-- ────────────────────────────────────────────────────────────
-- 3. Pipeline Metrics
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit.pipeline_metrics (
    metric_id           BIGSERIAL PRIMARY KEY,
    run_id              TEXT REFERENCES audit.pipeline_runs(run_id) ON DELETE SET NULL,
    metric_name         TEXT NOT NULL,
    metric_value        NUMERIC(12,4) NOT NULL,
    labels              JSONB NOT NULL DEFAULT '{}'::jsonb,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metrics_run ON audit.pipeline_metrics(run_id);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON audit.pipeline_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_metrics_recorded ON audit.pipeline_metrics(recorded_at DESC);

COMMENT ON TABLE audit.pipeline_metrics IS
    'Queryable pipeline metrics for analytics and diagnostics. Batch-inserted to avoid per-metric overhead.';

-- ────────────────────────────────────────────────────────────
-- 4. Source Status CHECK Constraint
-- ────────────────────────────────────────────────────────────

-- Enforce valid states at the database level.
-- Python enforces transitions; Postgres enforces validity.
-- Wrapped in a DO block so the ALTER TABLE is skipped (no lock acquired)
-- when the constraint already exists — avoids lock contention on busy tables.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'chk_source_status'
          AND table_schema = 'corpus'
          AND table_name = 'sources'
    ) THEN
        ALTER TABLE corpus.sources
            ADD CONSTRAINT chk_source_status
            CHECK (status IN (
                'discovered', 'fetched', 'extracted', 'condensed',
                'indexed', 'filtered_out', 'rejected', 'error',
                'retrying', 'dead_letter'
            ));
    END IF;
END $$;

-- ────────────────────────────────────────────────────────────
-- 5. Verification
-- ────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='audit' AND table_name='embedding_registry') THEN
        RAISE EXCEPTION 'Phase 14 migration failed: embedding_registry table not created';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='audit' AND table_name='dead_letter_queue') THEN
        RAISE EXCEPTION 'Phase 14 migration failed: dead_letter_queue table not created';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='audit' AND table_name='pipeline_metrics') THEN
        RAISE EXCEPTION 'Phase 14 migration failed: pipeline_metrics table not created';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'chk_source_status'
        AND table_schema = 'corpus' AND table_name = 'sources'
    ) THEN
        RAISE EXCEPTION 'Phase 14 migration failed: chk_source_status constraint not created';
    END IF;
    RAISE NOTICE 'Phase 14 migration verified: all tables and constraints created successfully';
END $$;

-- Migration complete.
