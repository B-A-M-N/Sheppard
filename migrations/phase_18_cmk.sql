-- Phase 18: Cognitive Memory Kernel (CMK)
-- Sheppard v1.3.0-phase18
--
-- Adds:
-- 1. cmk.concepts — Concept cluster persistence
-- 2. cmk.atom_embeddings — Cached embedding vectors
-- 3. cmk.feedback_log — Feedback loop audit trail
--
-- Concepts are the primary retrieval unit in CMK v2+.
-- Embeddings are cached per-atom for fast scoring.
-- Feedback log tracks reliability adjustments.

-- ────────────────────────────────────────────────────────────
-- 1. CMK Schema
-- ────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS cmk;

-- ────────────────────────────────────────────────────────────
-- 2. Concepts Table
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cmk.concepts (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    summary         TEXT NOT NULL,
    atom_ids        TEXT[] NOT NULL DEFAULT '{}',
    centroid        JSONB,
    reliability     NUMERIC(8,4) NOT NULL DEFAULT 0.5,
    centrality      NUMERIC(8,4) NOT NULL DEFAULT 0.5,
    topic_id        TEXT,
    mission_id      TEXT,
    relationships   JSONB NOT NULL DEFAULT '{"supports":[],"contradicts":[],"refines":[]}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_concepts_reliability ON cmk.concepts(reliability DESC);
CREATE INDEX IF NOT EXISTS idx_concepts_topic ON cmk.concepts(topic_id) WHERE topic_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_concepts_mission ON cmk.concepts(mission_id) WHERE mission_id IS NOT NULL;

-- GIN index on relationships for graph traversal queries
CREATE INDEX IF NOT EXISTS idx_concepts_relationships ON cmk.concepts USING GIN (relationships);

COMMENT ON TABLE cmk.concepts IS
    'CMK concept clusters — primary retrieval unit. Built from atom embeddings via KMeans/HDBSCAN.';

-- ────────────────────────────────────────────────────────────
-- 3. Atom Embeddings Table (persistent store, not just cache)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cmk.atom_embeddings (
    atom_id         TEXT NOT NULL REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE CASCADE,
    embedding       JSONB NOT NULL,
    model           TEXT NOT NULL DEFAULT 'nomic-embed-text',
    model_version   TEXT NOT NULL DEFAULT 'v1',
    dimension       INT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (atom_id, model)
);

CREATE INDEX IF NOT EXISTS idx_atom_embeddings_model ON cmk.atom_embeddings(model);

COMMENT ON TABLE cmk.atom_embeddings IS
    'Persistent embedding store for atoms. Redis is the cache layer; this is the source of truth.';

-- ────────────────────────────────────────────────────────────
-- 4. Feedback Log (audit trail for reliability adjustments)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cmk.feedback_log (
    id              BIGSERIAL PRIMARY KEY,
    response_id     TEXT,
    atom_id         TEXT NOT NULL REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE CASCADE,
    delta           NUMERIC(8,4) NOT NULL,
    old_reliability NUMERIC(8,4),
    new_reliability NUMERIC(8,4),
    response_quality NUMERIC(8,4) NOT NULL,
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_atom ON cmk.feedback_log(atom_id);
CREATE INDEX IF NOT EXISTS idx_feedback_response ON cmk.feedback_log(response_id) WHERE response_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_feedback_created ON cmk.feedback_log(created_at DESC);

COMMENT ON TABLE cmk.feedback_log IS
    'Audit trail for CMK feedback loop — tracks reliability adjustments per response.';

-- ────────────────────────────────────────────────────────────
-- 5. Trigger: updated_at on concepts
-- ────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION cmk.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_concepts_updated_at ON cmk.concepts;
CREATE TRIGGER trg_concepts_updated_at
    BEFORE UPDATE ON cmk.concepts
    FOR EACH ROW EXECUTE FUNCTION cmk.set_updated_at();

-- ────────────────────────────────────────────────────────────
-- 6. Verification
-- ────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='cmk' AND table_name='concepts'
    ) THEN
        RAISE EXCEPTION 'Phase 18 migration failed: cmk.concepts table not created';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='cmk' AND table_name='atom_embeddings'
    ) THEN
        RAISE EXCEPTION 'Phase 18 migration failed: cmk.atom_embeddings table not created';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='cmk' AND table_name='feedback_log'
    ) THEN
        RAISE EXCEPTION 'Phase 18 migration failed: cmk.feedback_log table not created';
    END IF;
    RAISE NOTICE 'Phase 18 migration verified: CMK schema created successfully';
END $$;

-- Migration complete.
