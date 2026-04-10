-- ============================================================
-- Phase 13: Foundation — Pipeline Audit & Source Status Tracking
-- Sheppard v1.3.0-phase13
--
-- Adds:
-- 1. audit.pipeline_runs table (replaces V2 distillation_log)
-- 2. filter_metadata JSONB on corpus.sources
-- 3. Soft CHECK constraint on filter reasons
-- 4. Status column comment documenting lifecycle
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. Audit Schema
-- ────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS audit;

-- Pipeline execution audit table
-- One row per pipeline run (extraction, condensation, synthesis, scraping)
-- Hybrid ownership: orchestrator writes start + final, stage functions update counters
CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
    run_id              TEXT PRIMARY KEY,
    mission_id          TEXT NOT NULL,
    topic_id            TEXT NOT NULL,
    pipeline_type       TEXT NOT NULL DEFAULT 'extraction',  -- extraction | condensation | synthesis | scraping
    pipeline_version    TEXT NOT NULL DEFAULT 'v1.3.0-phase13',
    status              TEXT NOT NULL DEFAULT 'running',     -- running | completed | failed

    -- Stage-level timestamps (updated by stage functions)
    stage_scraped       TIMESTAMPTZ,
    stage_extracted     TIMESTAMPTZ,
    stage_filtered      TIMESTAMPTZ,
    stage_condensed     TIMESTAMPTZ,

    -- Counters (updated incrementally during pipeline execution)
    source_count        INT DEFAULT 0,
    extracted_count     INT DEFAULT 0,
    filtered_out_count  INT DEFAULT 0,
    rejected_count      INT DEFAULT 0,
    atom_count          INT DEFAULT 0,

    -- Error tracking (dead-letter — written on failure)
    error_stage         TEXT,
    error_class         TEXT,
    error_detail        TEXT,
    error_traceback     TEXT,

    -- Timing
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    duration_secs       NUMERIC(10,3) GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (completed_at - started_at))
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_mission ON audit.pipeline_runs(mission_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON audit.pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started ON audit.pipeline_runs(started_at DESC);

-- ────────────────────────────────────────────────────────────
-- 2. Source Filter Metadata
-- ────────────────────────────────────────────────────────────

-- Track WHY sources were filtered (flexible JSONB, not hard ENUM)
ALTER TABLE corpus.sources
    ADD COLUMN IF NOT EXISTS filter_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Soft CHECK: guide toward canonical reason values without migration lock-in
-- New reasons can be added without a migration — just update the CHECK constraint
ALTER TABLE corpus.sources
    DROP CONSTRAINT IF EXISTS chk_source_filter_reason;

ALTER TABLE corpus.sources
    ADD CONSTRAINT chk_source_filter_reason
    CHECK (
        filter_metadata = '{}'::jsonb
        OR filter_metadata IS NULL
        OR (
            filter_metadata ? 'reason'
            AND filter_metadata->>'reason' IN (
                'too_short', 'low_quality', 'duplicate', 'semantic_drift', 'no_atoms'
            )
        )
    );

-- Document the full source status lifecycle
COMMENT ON COLUMN corpus.sources.status IS
    'Lifecycle: discovered -> fetched -> extracted -> filtered_out -> condensed | rejected | error';

-- ────────────────────────────────────────────────────────────
-- 3. Deprecation Notice
-- ────────────────────────────────────────────────────────────

-- distillation_log (V2, schema.sql line 593) is superseded by audit.pipeline_runs.
-- It is NOT dropped here — existing data may still be referenced by V2 code paths.
-- Future cleanup migration should:
-- 1. Verify no V2 code reads distillation_log
-- 2. Migrate any needed historical data to audit.pipeline_runs
-- 3. DROP TABLE distillation_log
COMMENT ON TABLE distillation_log IS
    'DEPRECATED (v1.3.0-phase13): Superseded by audit.pipeline_runs. Do not use for new writes.';

-- Migration complete.
