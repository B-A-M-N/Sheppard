-- Phase 19: Cognitive Architecture — CKS, Belief Graph, Activation Memory
-- Sheppard v1.4.0-phase19
--
-- Adds:
-- 1. canonical_knowledge — distilled truth layer (CKS)
-- 2. belief_nodes / belief_edges — global belief graph
-- 3. belief_versions — never overwrite truth, version it
-- 4. hypotheses — predicted missing structure
-- 5. activation tracking — Redis-backed activation memory
-- 6. atom enrichment — usage_count, last_accessed, confirmation_count
-- 7. concept_anchors — cross-domain abstraction hubs

-- ────────────────────────────────────────────────────────────
-- 1. Canonical Knowledge Store (CKS)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS canonical_knowledge (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id        UUID NOT NULL,

    claim           TEXT NOT NULL,
    confidence      NUMERIC(8,4) NOT NULL DEFAULT 0.5,

    supporting_atom_ids     TEXT[] DEFAULT '{}',
    contradicting_atom_ids  TEXT[] DEFAULT '{}',

    supporting_count    INT DEFAULT 0,
    contradicting_count INT DEFAULT 0,

    authority_score     NUMERIC(8,4) DEFAULT 0.0,
    stability_score     NUMERIC(8,4) DEFAULT 0.0,
    contradiction_pressure NUMERIC(8,4) DEFAULT 0.0,
    revision_count      INT DEFAULT 0,

    version         INT DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_canonical_topic ON canonical_knowledge(topic_id);
CREATE INDEX idx_canonical_authority ON canonical_knowledge(authority_score DESC);
CREATE INDEX idx_canonical_stability ON canonical_knowledge(stability_score DESC);

COMMENT ON TABLE canonical_knowledge IS
    'Distilled truth layer — synthesized from atoms, self-improving via reinforcement and contradiction resolution.';

-- ────────────────────────────────────────────────────────────
-- 2. Belief Graph — Nodes and Edges
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS belief_nodes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_id    UUID REFERENCES canonical_knowledge(id) ON DELETE SET NULL,

    claim           TEXT NOT NULL,
    domain          TEXT,

    authority_score     NUMERIC(8,4) DEFAULT 0.0,
    stability_score     NUMERIC(8,4) DEFAULT 0.0,
    contradiction_pressure NUMERIC(8,4) DEFAULT 0.0,
    revision_count      INT DEFAULT 0,

    embedding       VECTOR(768),  -- nomic-embed-text dimension
    embedding_model TEXT DEFAULT 'nomic-embed-text',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_belief_domain ON belief_nodes(domain) WHERE domain IS NOT NULL;
CREATE INDEX idx_belief_canonical ON belief_nodes(canonical_id) WHERE canonical_id IS NOT NULL;
CREATE INDEX idx_belief_authority ON belief_nodes(authority_score DESC);

-- pgvector index for similarity search (requires pgvector extension)
-- CREATE INDEX idx_belief_embedding ON belief_nodes USING ivfflat (embedding vector_cosine_ops);

COMMENT ON TABLE belief_nodes IS
    'Global belief graph nodes — canonical claims with authority, stability, and cross-domain embeddings.';

CREATE TABLE IF NOT EXISTS belief_edges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    from_node       UUID NOT NULL REFERENCES belief_nodes(id) ON DELETE CASCADE,
    to_node         UUID NOT NULL REFERENCES belief_nodes(id) ON DELETE CASCADE,

    relation_type   TEXT NOT NULL CHECK (relation_type IN (
        'supports', 'contradicts', 'implies', 'refines',
        'depends_on', 'analogous_to', 'instantiates', 'causes'
    )),

    strength        NUMERIC(8,4) NOT NULL CHECK (strength >= 0.0 AND strength <= 1.0),

    evidence_atom_ids TEXT[] DEFAULT '{}',
    reason          TEXT,  -- LLM-generated explanation for the edge

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (from_node, to_node, relation_type)
);

CREATE INDEX idx_belief_edges_from ON belief_edges(from_node);
CREATE INDEX idx_belief_edges_to ON belief_edges(to_node);
CREATE INDEX idx_belief_edges_type ON belief_edges(relation_type);
CREATE INDEX idx_belief_edges_strength ON belief_edges(strength DESC);

COMMENT ON TABLE belief_edges IS
    'Reasoning links between belief nodes. 8 relation types enable structured inference.';

-- ────────────────────────────────────────────────────────────
-- 3. Belief Versioning — Never Overwrite Truth
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS belief_versions (
    id              BIGSERIAL PRIMARY KEY,
    node_id         UUID NOT NULL REFERENCES belief_nodes(id) ON DELETE CASCADE,

    claim           TEXT NOT NULL,
    confidence      NUMERIC(8,4) NOT NULL,
    authority_score NUMERIC(8,4),
    stability_score NUMERIC(8,4),

    revision_reason TEXT,  -- why this version was created (modify, split, delete)
    revision_patch  JSONB, -- the LLM-generated patch that caused this version

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_belief_versions_node ON belief_versions(node_id);
CREATE INDEX idx_belief_versions_created ON belief_versions(created_at DESC);

COMMENT ON TABLE belief_versions IS
    'Evolution history of belief nodes. Truth is never deleted — only versioned.';

-- ────────────────────────────────────────────────────────────
-- 4. Hypotheses — Predicted Missing Structure
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS hypotheses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    node_a          UUID NOT NULL REFERENCES belief_nodes(id) ON DELETE CASCADE,
    node_b          UUID NOT NULL REFERENCES belief_nodes(id) ON DELETE CASCADE,

    hypothesis_type TEXT NOT NULL CHECK (hypothesis_type IN (
        'causal', 'analogical', 'corrective', 'relational'
    )),

    confidence      NUMERIC(8,4) DEFAULT 0.0,
    score           NUMERIC(8,4) DEFAULT 0.0,

    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'testing', 'confirmed', 'rejected', 'refined'
    )),

    evidence        JSONB,  -- supporting/contradicting evidence collected during testing
    test_result     JSONB,  -- LLM evaluation result

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tested_at       TIMESTAMPTZ,

    UNIQUE (node_a, node_b, hypothesis_type, status)
);

CREATE INDEX idx_hypotheses_status ON hypotheses(status);
CREATE INDEX idx_hypotheses_score ON hypotheses(score DESC);
CREATE INDEX idx_hypotheses_node_a ON hypotheses(node_a);
CREATE INDEX idx_hypotheses_node_b ON hypotheses(node_b);
CREATE INDEX idx_hypotheses_type ON hypotheses(hypothesis_type);

COMMENT ON TABLE hypotheses IS
    'Predicted missing edges in the belief graph — system-generated research questions.';

-- ────────────────────────────────────────────────────────────
-- 5. Concept Anchors — Cross-Domain Abstraction Hubs
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS concept_anchors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    name            TEXT NOT NULL,
    description     TEXT,

    embedding       VECTOR(768),
    embedding_model TEXT DEFAULT 'nomic-embed-text',

    domain_count    INT DEFAULT 1,
    domains         TEXT[] DEFAULT '{}',
    belief_count    INT DEFAULT 0,

    authority_score NUMERIC(8,4) DEFAULT 0.0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (name)
);

CREATE INDEX idx_concept_name ON concept_anchors(name);
CREATE INDEX idx_concept_authority ON concept_anchors(authority_score DESC);

COMMENT ON TABLE concept_anchors IS
    'Cross-domain abstraction hubs (e.g., "optimization", "feedback loop") that enable structural reasoning across topics.';

-- Junction table: belief_nodes ↔ concept_anchors
CREATE TABLE IF NOT EXISTS belief_concept_links (
    belief_id   UUID NOT NULL REFERENCES belief_nodes(id) ON DELETE CASCADE,
    concept_id  UUID NOT NULL REFERENCES concept_anchors(id) ON DELETE CASCADE,
    relevance   NUMERIC(8,4) DEFAULT 0.5,
    PRIMARY KEY (belief_id, concept_id)
);

CREATE INDEX idx_belief_concept_concept ON belief_concept_links(concept_id);

COMMENT ON TABLE belief_concept_links IS
    'Links belief nodes to concept anchors — enables cross-domain traversal.';

-- ────────────────────────────────────────────────────────────
-- 6. Atom Enrichment — Tracking Hooks
-- ────────────────────────────────────────────────────────────

ALTER TABLE knowledge.knowledge_atoms
ADD COLUMN IF NOT EXISTS usage_count INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_accessed TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS confirmation_count INT DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_atoms_usage ON knowledge.knowledge_atoms(usage_count DESC);
CREATE INDEX IF NOT EXISTS idx_atoms_last_accessed ON knowledge.knowledge_atoms(last_accessed DESC);

COMMENT ON COLUMN knowledge.knowledge_atoms.usage_count IS
    'How many times this atom was retrieved/used — implicit importance learning.';

COMMENT ON COLUMN knowledge.knowledge_atoms.last_accessed IS
    'When this atom was last used — enables activation decay.';

COMMENT ON COLUMN knowledge.knowledge_atoms.confirmation_count IS
    'How many independent sources have confirmed this atom.';

-- ────────────────────────────────────────────────────────────
-- 7. Activation Tracking — Helper Table for Decay
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cmk.activation_tracking (
    atom_id         TEXT NOT NULL REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE CASCADE,
    activation_score NUMERIC(8,4) NOT NULL DEFAULT 0.0,
    last_accessed   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (atom_id)
);

CREATE INDEX idx_activation_score ON cmk.activation_tracking(activation_score DESC);

COMMENT ON TABLE cmk.activation_tracking IS
    'Working memory layer — activation scores decay over time. Knowledge persists; access priority fades.';

-- ────────────────────────────────────────────────────────────
-- 8. Trigger: updated_at on versioned tables
-- ────────────────────────────────────────────────────────────

DROP TRIGGER IF EXISTS trg_canonical_updated ON canonical_knowledge;
CREATE TRIGGER trg_canonical_updated
    BEFORE UPDATE ON canonical_knowledge
    FOR EACH ROW EXECUTE FUNCTION cmk.set_updated_at();

DROP TRIGGER IF EXISTS trg_belief_updated ON belief_nodes;
CREATE TRIGGER trg_belief_updated
    BEFORE UPDATE ON belief_nodes
    FOR EACH ROW EXECUTE FUNCTION cmk.set_updated_at();

DROP TRIGGER IF EXISTS trg_concept_updated ON concept_anchors;
CREATE TRIGGER trg_concept_updated
    BEFORE UPDATE ON concept_anchors
    FOR EACH ROW EXECUTE FUNCTION cmk.set_updated_at();

-- ────────────────────────────────────────────────────────────
-- 9. Verification
-- ────────────────────────────────────────────────────────────

DO $$
DECLARE
    v_count INT;
BEGIN
    SELECT COUNT(*) INTO v_count FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'canonical_knowledge';
    IF v_count = 0 THEN RAISE EXCEPTION 'canonical_knowledge table not created'; END IF;

    SELECT COUNT(*) INTO v_count FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'belief_nodes';
    IF v_count = 0 THEN RAISE EXCEPTION 'belief_nodes table not created'; END IF;

    SELECT COUNT(*) INTO v_count FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'belief_edges';
    IF v_count = 0 THEN RAISE EXCEPTION 'belief_edges table not created'; END IF;

    SELECT COUNT(*) INTO v_count FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'hypotheses';
    IF v_count = 0 THEN RAISE EXCEPTION 'hypotheses table not created'; END IF;

    SELECT COUNT(*) INTO v_count FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'concept_anchors';
    IF v_count = 0 THEN RAISE EXCEPTION 'concept_anchors table not created'; END IF;

    RAISE NOTICE 'Phase 19 migration verified: Cognitive Architecture schema created successfully';
END $$;

-- Migration complete.
