-- ============================================================
-- Sheppard V2 — Full Postgres Schema (Revised)
--
-- Distillation levels:
--   Level A  raw_sources          (100% — audit layer)
--   Level B  knowledge_atoms      (10-15% — typed structured claims)
--   Level C  thematic_syntheses   (3-5% — grouped concept artifacts)
--   Level D  advisory_briefs      (<1% — operational brief per topic)
--
-- Additional layers:
--   crawl_sessions    — session memory (reproducibility)
--   novelty_scores    — stop condition signals per session
--   source_quality    — trust / authority scoring per domain
--   meta_memory       — system self-improvement tracking
--   concept graph     — Postgres adjacency list (no Neo4j)
--   project graph     — project artifacts + cross-links to domain knowledge
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- for query perf tracking


-- ════════════════════════════════════════════════════════════
-- SECTION 1: TOPIC + CRAWL SESSION MANAGEMENT
-- ════════════════════════════════════════════════════════════

-- ────────────────────────────────────────────────────────────
-- DOMAIN PROFILES — Configures how the refinery handles a domain
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS domain_profiles (
    profile_id          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    domain_type         TEXT NOT NULL,
    description         TEXT,
    config_json         JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- TOPICS — long-lived domain knowledge containers
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS topics (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_id          TEXT REFERENCES domain_profiles(profile_id) ON DELETE SET NULL,
    name                TEXT NOT NULL UNIQUE,
    description         TEXT,
    -- Budget tracking
    raw_bytes_total     BIGINT DEFAULT 0,
    level_b_bytes       BIGINT DEFAULT 0,
    level_c_bytes       BIGINT DEFAULT 0,
    level_d_bytes       BIGINT DEFAULT 0,
    -- Status
    crawl_status        TEXT DEFAULT 'idle',    -- idle | crawling | condensing | done | paused
    distillation_status TEXT DEFAULT 'none',    -- none | partial | complete
    -- Quality signals
    source_count        INT DEFAULT 0,
    atom_count          INT DEFAULT 0,
    contradiction_count INT DEFAULT 0,
    avg_source_trust    FLOAT DEFAULT 0.0,
    -- Timestamps
    first_crawled_at    TIMESTAMPTZ,
    last_updated_at     TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- CRAWL_SESSIONS — one record per /learn invocation
-- This is the session memory / reproducibility layer
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS crawl_sessions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic_id            UUID REFERENCES topics(id) ON DELETE CASCADE,
    -- Job config (what was requested)
    seed_query          TEXT NOT NULL,
    ceiling_bytes       BIGINT NOT NULL,
    max_doc_count       INT,
    allowed_source_types TEXT[],               -- web | academic | pdf | local
    dedupe_threshold    FLOAT DEFAULT 0.92,
    academic_only       BOOLEAN DEFAULT FALSE,
    -- Stop conditions hit
    stop_reason         TEXT,                  -- byte_cap | novelty_floor | diversity_sat | doc_cap | manual
    -- Execution stats
    docs_attempted      INT DEFAULT 0,
    docs_accepted       INT DEFAULT 0,
    docs_rejected_dedup INT DEFAULT 0,
    docs_rejected_quality INT DEFAULT 0,
    bytes_acquired      BIGINT DEFAULT 0,
    unique_domains      INT DEFAULT 0,
    -- Synthesis outputs produced
    atoms_generated     INT DEFAULT 0,
    syntheses_generated INT DEFAULT 0,
    brief_generated     BOOLEAN DEFAULT FALSE,
    -- Unresolved gaps flagged during synthesis
    open_gaps           TEXT[],
    -- Timing
    started_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    duration_secs       FLOAT
);

CREATE INDEX IF NOT EXISTS idx_sessions_topic ON crawl_sessions(topic_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON crawl_sessions(stop_reason);


-- ════════════════════════════════════════════════════════════
-- SECTION 2: LEVEL A — RAW EVIDENCE LAYER
-- ════════════════════════════════════════════════════════════

-- ────────────────────────────────────────────────────────────
-- SOURCES — one record per crawled page/document
-- Upgraded with quality scoring + acquisition invariants
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sources (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic_id            UUID REFERENCES topics(id) ON DELETE CASCADE,
    session_id          UUID REFERENCES crawl_sessions(id) ON DELETE SET NULL,
    -- Identity
    url                 TEXT NOT NULL,
    title               TEXT,
    domain              TEXT,
    source_type         TEXT DEFAULT 'web',    -- web | academic | pdf | local
    -- Content
    raw_bytes           BIGINT DEFAULT 0,
    content_hash        TEXT NOT NULL,         -- MD5 of cleaned content (dedup key)
    raw_file_path       TEXT,                  -- path on disk to raw markdown file
    -- Acquisition invariants
    crawl_depth         INT DEFAULT 0,         -- how many hops from seed URL
    crawl_lineage       TEXT[],                -- parent URL chain
    captured_at         TIMESTAMPTZ DEFAULT NOW(),
    content_date        TIMESTAMPTZ,           -- publication date if extractable
    -- Quality / trust
    trust_score         FLOAT DEFAULT 0.5,     -- 0.0-1.0, set by source_quality lookup
    quality_score       FLOAT DEFAULT 0.5,     -- doc-level content quality
    boilerplate_ratio   FLOAT DEFAULT 0.0,     -- fraction stripped as boilerplate
    novelty_score       FLOAT DEFAULT 1.0,     -- how novel vs existing corpus at ingest time
    -- Processing state
    distillation_level  INT DEFAULT 0,         -- highest level produced from this source (0-4)
    condensed           BOOLEAN DEFAULT FALSE,
    UNIQUE(topic_id, content_hash)             -- dedup by content, not URL
);

CREATE INDEX IF NOT EXISTS idx_sources_topic ON sources(topic_id);
CREATE INDEX IF NOT EXISTS idx_sources_session ON sources(session_id);
CREATE INDEX IF NOT EXISTS idx_sources_condensed ON sources(condensed);
CREATE INDEX IF NOT EXISTS idx_sources_trust ON sources(trust_score);
CREATE INDEX IF NOT EXISTS idx_sources_novelty ON sources(novelty_score);
CREATE INDEX IF NOT EXISTS idx_sources_hash ON sources(content_hash);

-- ────────────────────────────────────────────────────────────
-- SOURCE_QUALITY — per-domain trust registry
-- Populated over time via meta-memory feedback
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS source_quality (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain              TEXT NOT NULL UNIQUE,
    source_class        TEXT DEFAULT 'web',    -- academic | government | industry | blog | forum | unknown
    -- Trust signals
    base_trust          FLOAT DEFAULT 0.5,     -- static domain-level trust
    observed_trust      FLOAT,                 -- updated from meta-memory feedback
    peer_reviewed       BOOLEAN DEFAULT FALSE,
    citation_authority  FLOAT DEFAULT 0.5,     -- how often cited by other trusted sources
    -- Freshness
    avg_content_age_days INT,
    -- Usage stats
    times_crawled       INT DEFAULT 0,
    times_cited_in_atoms INT DEFAULT 0,
    times_contradicted  INT DEFAULT 0,
    -- Metadata
    notes               TEXT,
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sq_domain ON source_quality(domain);
CREATE INDEX IF NOT EXISTS idx_sq_class ON source_quality(source_class);

-- Pre-populate academic whitelist with high base trust
INSERT INTO source_quality (domain, source_class, base_trust, peer_reviewed) VALUES
    ('arxiv.org',                    'academic',   0.90, TRUE),
    ('pubmed.ncbi.nlm.nih.gov',      'academic',   0.95, TRUE),
    ('scholar.google.com',           'academic',   0.85, FALSE),
    ('semanticscholar.org',          'academic',   0.85, FALSE),
    ('acm.org',                      'academic',   0.92, TRUE),
    ('ieee.org',                     'academic',   0.92, TRUE),
    ('nature.com',                   'academic',   0.95, TRUE),
    ('science.org',                  'academic',   0.95, TRUE),
    ('springer.com',                 'academic',   0.88, TRUE),
    ('docs.python.org',              'industry',   0.90, FALSE),
    ('github.com',                   'industry',   0.70, FALSE),
    ('stackoverflow.com',            'forum',      0.60, FALSE)
ON CONFLICT (domain) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- NOVELTY_SCORES — per-session corpus novelty tracking
-- Feeds stop conditions (crawl stops when novelty floor is hit)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS novelty_scores (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          UUID REFERENCES crawl_sessions(id) ON DELETE CASCADE,
    topic_id            UUID REFERENCES topics(id) ON DELETE CASCADE,
    -- Measured after each N documents
    doc_sequence        INT NOT NULL,          -- document number in session when measured
    rolling_novelty     FLOAT NOT NULL,        -- avg novelty of last N docs (0-1)
    corpus_coverage     FLOAT,                 -- estimated % of topic subtopics covered
    source_diversity    FLOAT,                 -- unique domains / total docs ratio
    repetition_ratio    FLOAT,                 -- fraction of last N docs near-duplicate
    -- Stop signal
    below_floor         BOOLEAN DEFAULT FALSE, -- True when rolling_novelty < threshold
    measured_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_novelty_session ON novelty_scores(session_id);
CREATE INDEX IF NOT EXISTS idx_novelty_floor ON novelty_scores(below_floor);


-- ════════════════════════════════════════════════════════════
-- SECTION 3: LEVEL B — ATOMIC KNOWLEDGE LAYER
-- Typed structured claims extracted from sources
-- This is the "claims must be separable from interpretation" layer
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS knowledge_atoms (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic_id            UUID REFERENCES topics(id) ON DELETE CASCADE,
    session_id          UUID REFERENCES crawl_sessions(id) ON DELETE SET NULL,
    -- Content
    atom_type           TEXT NOT NULL,
    -- claim | definition | procedure | comparison | constraint |
    -- open_question | disagreement | example | failure_mode | best_practice
    content             TEXT NOT NULL,         -- the atomic statement itself
    -- Provenance (invariant: every atom must have a source)
    source_ids          UUID[],                -- supporting source IDs (min 1)
    citation_keys       TEXT[],                -- [S1], [S2] etc
    verbatim_excerpt    TEXT,                  -- ≤500 char supporting snippet from source
    -- Epistemic metadata
    confidence          FLOAT DEFAULT 0.7,     -- 0-1, how confident the extraction was
    is_contested        BOOLEAN DEFAULT FALSE, -- True if other atoms contradict this
    contesting_atom_ids UUID[],               -- IDs of contradicting atoms
    is_time_sensitive   BOOLEAN DEFAULT FALSE,
    valid_as_of         TIMESTAMPTZ,           -- for time-sensitive claims
    -- Universal Schema Additions
    scope_json          JSONB DEFAULT '{}',
    qualifiers_json     JSONB DEFAULT '{}',
    lineage_json        JSONB DEFAULT '{}',
    reuse_json          JSONB DEFAULT '{}',
    -- Indexing
    chroma_chunk_id     TEXT,                  -- link back to ChromaDB for semantic retrieval
    importance          FLOAT DEFAULT 0.5,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_atoms_topic ON knowledge_atoms(topic_id);
CREATE INDEX IF NOT EXISTS idx_atoms_type ON knowledge_atoms(atom_type);
CREATE INDEX IF NOT EXISTS idx_atoms_contested ON knowledge_atoms(is_contested);
CREATE INDEX IF NOT EXISTS idx_atoms_confidence ON knowledge_atoms(confidence);
CREATE INDEX IF NOT EXISTS idx_atoms_content ON knowledge_atoms USING gin(content gin_trgm_ops);

-- ────────────────────────────────────────────────────────────
-- ATOM_SOURCE_LINKS — explicit many-to-many between atoms and sources
-- Ensures every atom is traceable to its evidence
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS atom_source_links (
    atom_id             UUID REFERENCES knowledge_atoms(id) ON DELETE CASCADE,
    source_id           UUID REFERENCES sources(id) ON DELETE CASCADE,
    citation_key        TEXT,
    excerpt             TEXT,                  -- ≤500 chars verbatim support
    PRIMARY KEY (atom_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_asl_atom ON atom_source_links(atom_id);
CREATE INDEX IF NOT EXISTS idx_asl_source ON atom_source_links(source_id);

-- ────────────────────────────────────────────────────────────
-- CONTRADICTIONS — explicit contradiction registry
-- Contradictions must be RETAINED, not averaged away
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contradictions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic_id            UUID REFERENCES topics(id) ON DELETE CASCADE,
    atom_a_id           UUID REFERENCES knowledge_atoms(id) ON DELETE CASCADE,
    atom_b_id           UUID REFERENCES knowledge_atoms(id) ON DELETE CASCADE,
    description         TEXT,                  -- LLM-written description of the disagreement
    resolution          TEXT,                  -- NULL if unresolved; else explanation
    resolved            BOOLEAN DEFAULT FALSE,
    detected_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contra_topic ON contradictions(topic_id);
CREATE INDEX IF NOT EXISTS idx_contra_resolved ON contradictions(resolved);


-- ════════════════════════════════════════════════════════════
-- SECTION 4: CONCEPT GRAPH (spans Level B and C)
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS concepts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic_id            UUID REFERENCES topics(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    concept_type        TEXT DEFAULT 'general',
    -- tool | algorithm | pattern | principle | person | org | general
    definition          TEXT,                  -- condensed 1-3 sentence definition
    -- Importance
    importance          FLOAT DEFAULT 0.5,
    mention_count       INT DEFAULT 1,         -- how often it appeared across sources
    -- Linkage
    chroma_chunk_id     TEXT,
    primary_atom_ids    UUID[],                -- Level B atoms that define this concept
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(topic_id, name)
);

CREATE INDEX IF NOT EXISTS idx_concepts_topic ON concepts(topic_id);
CREATE INDEX IF NOT EXISTS idx_concepts_name ON concepts USING gin(name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_concepts_importance ON concepts(importance DESC);

CREATE TABLE IF NOT EXISTS concept_relationships (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id           UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    target_id           UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    relationship        TEXT NOT NULL,
    -- implements | depends_on | contrasts_with | extends | uses |
    -- precedes | enables | conflicts_with | is_alternative_to
    weight              FLOAT DEFAULT 1.0,
    evidence_atom_ids   UUID[],                -- atoms that support this relationship
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_id, target_id, relationship)
);

CREATE INDEX IF NOT EXISTS idx_rel_source ON concept_relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_rel_target ON concept_relationships(target_id);

-- ════════════════════════════════════════════════════════════
-- SECTION 5: LEVEL C — THEMATIC SYNTHESIS LAYER
-- Grouped concept artifacts: tradeoffs, failure modes, best practices
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS thematic_syntheses (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic_id            UUID REFERENCES topics(id) ON DELETE CASCADE,
    session_id          UUID REFERENCES crawl_sessions(id) ON DELETE SET NULL,
    -- Classification
    synthesis_type      TEXT NOT NULL,
    -- concept_map | topic_summary | chronology | ecosystem_map |
    -- design_tradeoffs | failure_modes | best_practices | open_problems
    title               TEXT,
    content             TEXT NOT NULL,         -- dense prose synthesis
    -- Provenance
    source_atom_ids     UUID[],                -- Level B atoms that fed this
    source_chunk_ids    TEXT[],                -- ChromaDB chunk IDs
    -- Quality
    confidence          FLOAT DEFAULT 0.7,
    coverage_score      FLOAT DEFAULT 0.5,     -- how completely this covers the subtopic
    fidelity_score      FLOAT DEFAULT 0.7,     -- set by meta-memory after retrieval feedback
    -- Indexing
    chroma_chunk_id     TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_synth_topic ON thematic_syntheses(topic_id);
CREATE INDEX IF NOT EXISTS idx_synth_type ON thematic_syntheses(synthesis_type);
CREATE INDEX IF NOT EXISTS idx_synth_confidence ON thematic_syntheses(confidence DESC);


-- ════════════════════════════════════════════════════════════
-- SECTION 6: LEVEL D — ADVISORY BRIEF LAYER
-- One brief per topic per session — the "what matters" layer
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS advisory_briefs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic_id            UUID REFERENCES topics(id) ON DELETE CASCADE,
    session_id          UUID REFERENCES crawl_sessions(id) ON DELETE SET NULL,
    -- Structured advisory content
    what_matters        TEXT,                  -- top 3-5 key takeaways
    what_is_contested   TEXT,                  -- active disagreements in the field
    what_is_likely_true TEXT,                  -- high-confidence consensus claims
    what_needs_testing  TEXT,                  -- claims that need validation before trusting
    how_applies_to_projects TEXT,              -- LLM-generated project linkage notes
    open_questions      TEXT[],                -- unresolved questions flagged during synthesis
    -- Provenance
    source_synthesis_ids UUID[],               -- Level C syntheses that fed this
    -- Quality
    confidence          FLOAT DEFAULT 0.7,
    staleness_days      INT DEFAULT 0,         -- days since last update; drives decay
    -- Indexing
    chroma_chunk_id     TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_brief_topic ON advisory_briefs(topic_id);
CREATE INDEX IF NOT EXISTS idx_brief_session ON advisory_briefs(session_id);

CREATE TABLE IF NOT EXISTS brief_sections (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    brief_id            UUID REFERENCES advisory_briefs(id) ON DELETE CASCADE,
    section_order       INT NOT NULL,
    title               TEXT NOT NULL,
    content             TEXT,
    supporting_atom_ids UUID[] DEFAULT '{}',
    contradiction_ids   UUID[] DEFAULT '{}',
    unresolved_ambiguities TEXT[] DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_brief_sections_brief ON brief_sections(brief_id);

-- ────────────────────────────────────────────────────────────
-- AUTHORITY SILOS — The Domain Capital Base (Layer D+)
-- Maps the four strata into a single, queryable expert asset
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS authority_silos (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic_id            UUID REFERENCES topics(id) ON DELETE CASCADE UNIQUE,
    name                TEXT NOT NULL,
    domain_boundaries   TEXT,                  -- what this covers and what it excludes
    canonical_terminology JSONB DEFAULT '{}',  -- strict definitions mapping
    -- Atom pointers categorized by operational utility
    core_definitions    UUID[] DEFAULT '{}',
    established_mechanisms UUID[] DEFAULT '{}',
    high_confidence_truths UUID[] DEFAULT '{}',
    known_contradictions UUID[] DEFAULT '{}',
    failure_patterns    UUID[] DEFAULT '{}',
    implementation_guidance UUID[] DEFAULT '{}',
    -- Link back to the coherent narrative
    linked_brief_id     UUID REFERENCES advisory_briefs(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_authority_silos_topic ON authority_silos(topic_id);


-- ════════════════════════════════════════════════════════════
-- SECTION 7: CITATIONS
-- Stable [Sn] keys traceable from Level D all the way to Level A
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS citations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic_id            UUID REFERENCES topics(id) ON DELETE CASCADE,
    source_id           UUID REFERENCES sources(id) ON DELETE CASCADE,
    atom_id             UUID REFERENCES knowledge_atoms(id) ON DELETE SET NULL,
    citation_key        TEXT NOT NULL,         -- [S1], [S2] etc — stable across sessions
    excerpt             TEXT,                  -- ≤500 char verbatim snippet
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(topic_id, citation_key)
);

CREATE INDEX IF NOT EXISTS idx_citations_topic ON citations(topic_id);
CREATE INDEX IF NOT EXISTS idx_citations_key ON citations(citation_key);
CREATE INDEX IF NOT EXISTS idx_citations_atom ON citations(atom_id);


-- ════════════════════════════════════════════════════════════
-- SECTION 8: PROJECT GRAPH
-- Separate graph for your own repos/products
-- Cross-linked to domain knowledge via project_knowledge_links
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS projects (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                TEXT NOT NULL UNIQUE,
    description         TEXT,
    repo_url            TEXT,
    local_path          TEXT,
    chroma_collection   TEXT,                  -- e.g. "project_sollol"
    -- Project graph stats
    file_count          INT DEFAULT 0,
    module_count        INT DEFAULT 0,
    last_indexed_at     TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Project artifact types: files, modules, interfaces, design docs, TODOs, etc.
CREATE TABLE IF NOT EXISTS project_artifacts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id          UUID REFERENCES projects(id) ON DELETE CASCADE,
    artifact_type       TEXT NOT NULL,
    -- file | module | interface | design_doc | todo | arch_decision |
    -- test_failure | benchmark | bug_cluster | ticket
    name                TEXT NOT NULL,
    path                TEXT,                  -- relative path in repo
    content_summary     TEXT,                  -- LLM-generated 2-3 sentence summary
    content_hash        TEXT,
    chroma_chunk_id     TEXT,
    -- Metadata
    language            TEXT,                  -- for code files
    status              TEXT DEFAULT 'active', -- active | deprecated | wip
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, path)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_project ON project_artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON project_artifacts(artifact_type);

CREATE TABLE IF NOT EXISTS application_queries (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id          UUID REFERENCES projects(id) ON DELETE CASCADE,
    query_type          TEXT NOT NULL,
    title               TEXT NOT NULL,
    payload_json        JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Cross-links: external concept/atom ↔ internal project artifact
-- This is where "external failure mode ↔ internal risk point" gets stored
CREATE TABLE IF NOT EXISTS project_knowledge_links (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id          UUID REFERENCES projects(id) ON DELETE CASCADE,
    artifact_id         UUID REFERENCES project_artifacts(id) ON DELETE CASCADE,
    -- Link target (one of these is set)
    concept_id          UUID REFERENCES concepts(id) ON DELETE SET NULL,
    atom_id             UUID REFERENCES knowledge_atoms(id) ON DELETE SET NULL,
    synthesis_id        UUID REFERENCES thematic_syntheses(id) ON DELETE SET NULL,
    -- Link metadata
    link_type           TEXT NOT NULL,
    -- applies | implements | gaps | risks | opportunities | contradicts | validates
    relevance           FLOAT DEFAULT 0.5,
    application_note    TEXT,                  -- LLM-generated note on how it applies
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, artifact_id, concept_id, atom_id)
);

CREATE INDEX IF NOT EXISTS idx_pkl_project ON project_knowledge_links(project_id);
CREATE INDEX IF NOT EXISTS idx_pkl_artifact ON project_knowledge_links(artifact_id);
CREATE INDEX IF NOT EXISTS idx_pkl_type ON project_knowledge_links(link_type);


-- ════════════════════════════════════════════════════════════
-- SECTION 9: META-MEMORY
-- Tracks system self-improvement signals over time
-- Which sources are reliable, which passes lose fidelity,
-- which retrieval strategies produce strong reasoning
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS meta_memory (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- What this record is about
    entity_type         TEXT NOT NULL,
    -- source_domain | synthesis_pass | retrieval_query | prompt_pattern | topic
    entity_id           TEXT NOT NULL,         -- UUID or domain string
    -- Observation
    observation_type    TEXT NOT NULL,
    -- source_reliability | synthesis_fidelity | retrieval_quality |
    -- prompt_effectiveness | domain_coverage | contradiction_rate
    score               FLOAT,                 -- 0.0-1.0 signal strength
    notes               TEXT,                  -- free text observation
    -- Context
    topic_id            UUID REFERENCES topics(id) ON DELETE SET NULL,
    session_id          UUID REFERENCES crawl_sessions(id) ON DELETE SET NULL,
    -- Promotion gates
    -- domain memory → advisory memory requires repeated_utility > threshold
    utility_count       INT DEFAULT 1,         -- times this entity has been useful
    -- Decay
    last_observed_at    TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_meta_entity ON meta_memory(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_meta_observation ON meta_memory(observation_type);
CREATE INDEX IF NOT EXISTS idx_meta_score ON meta_memory(score DESC);
CREATE INDEX IF NOT EXISTS idx_meta_topic ON meta_memory(topic_id);

-- ────────────────────────────────────────────────────────────
-- KNOWLEDGE_PROMOTION_LOG — tracks when knowledge moves
-- between session → domain → advisory memory tiers
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_promotion_log (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type         TEXT NOT NULL,         -- atom | synthesis | concept | brief
    entity_id           UUID NOT NULL,
    from_tier           TEXT NOT NULL,         -- session | domain | advisory
    to_tier             TEXT NOT NULL,
    promotion_reason    TEXT,                  -- relevance_threshold | repeated_utility | manual
    relevance_score     FLOAT,
    utility_count       INT,
    promoted_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_promo_entity ON knowledge_promotion_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_promo_tier ON knowledge_promotion_log(from_tier, to_tier);


-- ════════════════════════════════════════════════════════════
-- SECTION 10: DISTILLATION LOG (replaces old condensation_log)
-- Tracks what level artifacts were produced and their fidelity
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS distillation_log (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic_id            UUID REFERENCES topics(id) ON DELETE CASCADE,
    session_id          UUID REFERENCES crawl_sessions(id) ON DELETE SET NULL,
    trigger_type        TEXT NOT NULL,         -- threshold_70 | threshold_85 | threshold_95 | manual
    -- What was produced
    level_b_atoms       INT DEFAULT 0,
    level_c_syntheses   INT DEFAULT 0,
    level_d_brief       BOOLEAN DEFAULT FALSE,
    -- Size accounting
    raw_bytes_consumed  BIGINT DEFAULT 0,
    level_b_bytes       BIGINT DEFAULT 0,
    level_c_bytes       BIGINT DEFAULT 0,
    level_d_bytes       BIGINT DEFAULT 0,
    -- Quality signals recorded
    avg_atom_confidence FLOAT,
    contradiction_rate  FLOAT,                 -- contradictions / atoms
    fidelity_estimate   FLOAT,                 -- crude estimate of information preserved
    -- Timing
    started_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    duration_secs       FLOAT
);

CREATE INDEX IF NOT EXISTS idx_distlog_topic ON distillation_log(topic_id);


-- ════════════════════════════════════════════════════════════
-- SECTION 11: USEFUL VIEWS
-- ════════════════════════════════════════════════════════════

-- Topic health at a glance
CREATE OR REPLACE VIEW topic_health AS
SELECT
    t.id,
    t.name,
    t.crawl_status,
    t.distillation_status,
    t.source_count,
    t.atom_count,
    t.contradiction_count,
    ROUND(t.avg_source_trust::NUMERIC, 2)       AS avg_trust,
    ROUND((t.level_b_bytes::FLOAT / NULLIF(t.raw_bytes_total, 0) * 100)::NUMERIC, 1) AS level_b_pct,
    ROUND((t.level_c_bytes::FLOAT / NULLIF(t.raw_bytes_total, 0) * 100)::NUMERIC, 1) AS level_c_pct,
    ROUND((t.level_d_bytes::FLOAT / NULLIF(t.raw_bytes_total, 0) * 100)::NUMERIC, 1) AS level_d_pct,
    COUNT(DISTINCT cn.id)                       AS unresolved_contradictions,
    t.last_updated_at
FROM topics t
LEFT JOIN contradictions cn ON cn.topic_id = t.id AND cn.resolved = FALSE
GROUP BY t.id;

-- Per-session novelty trend (for stop condition monitoring)
CREATE OR REPLACE VIEW session_novelty_trend AS
SELECT
    ns.session_id,
    cs.seed_query,
    ns.doc_sequence,
    ROUND(ns.rolling_novelty::NUMERIC, 3)  AS novelty,
    ROUND(ns.source_diversity::NUMERIC, 3) AS diversity,
    ROUND(ns.repetition_ratio::NUMERIC, 3) AS repetition,
    ns.below_floor,
    ns.measured_at
FROM novelty_scores ns
JOIN crawl_sessions cs ON cs.id = ns.session_id
ORDER BY ns.session_id, ns.doc_sequence;

-- Contested knowledge — all unresolved contradictions with their atoms
CREATE OR REPLACE VIEW contested_knowledge AS
SELECT
    c.topic_id,
    t.name                          AS topic_name,
    c.id                            AS contradiction_id,
    a.content                       AS atom_a,
    a.atom_type                     AS type_a,
    b.content                       AS atom_b,
    b.atom_type                     AS type_b,
    c.description,
    c.detected_at
FROM contradictions c
JOIN knowledge_atoms a ON a.id = c.atom_a_id
JOIN knowledge_atoms b ON b.id = c.atom_b_id
JOIN topics t ON t.id = c.topic_id
WHERE c.resolved = FALSE;

-- Project gap analysis — project artifacts without linked knowledge
CREATE OR REPLACE VIEW project_knowledge_gaps AS
SELECT
    p.name                          AS project,
    pa.artifact_type,
    pa.name                         AS artifact,
    pa.path,
    pa.content_summary
FROM project_artifacts pa
JOIN projects p ON p.id = pa.project_id
WHERE pa.id NOT IN (
    SELECT artifact_id FROM project_knowledge_links
)
AND pa.status = 'active';


-- ════════════════════════════════════════════════════════════
-- SECTION 12: RECURSIVE CTE FOR CONCEPT GRAPH TRAVERSAL
-- ════════════════════════════════════════════════════════════

-- Run from Python (psycopg2/asyncpg) with :start_id and :max_depth params:
--
-- WITH RECURSIVE graph AS (
--     -- Seed: direct neighbors of the start concept
--     SELECT
--         cr.source_id,
--         cr.target_id,
--         cr.relationship,
--         cr.weight,
--         1 AS depth,
--         ARRAY[cr.source_id] AS visited        -- cycle prevention
--     FROM concept_relationships cr
--     WHERE cr.source_id = :start_id
--
--   UNION ALL
--
--     -- Recursive: expand one hop at a time
--     SELECT
--         cr.source_id,
--         cr.target_id,
--         cr.relationship,
--         cr.weight,
--         g.depth + 1,
--         g.visited || cr.source_id
--     FROM concept_relationships cr
--     JOIN graph g ON cr.source_id = g.target_id
--     WHERE g.depth < :max_depth
--       AND cr.target_id <> ALL(g.visited)      -- no cycles
-- )
-- SELECT DISTINCT
--     c.id,
--     c.name,
--     c.concept_type,
--     c.definition,
--     c.importance,
--     g.relationship,
--     g.depth,
--     g.weight
-- FROM graph g
-- JOIN concepts c ON c.id = g.target_id
-- ORDER BY g.depth ASC, g.weight DESC, c.importance DESC;
