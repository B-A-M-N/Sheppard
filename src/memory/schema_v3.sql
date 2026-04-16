-- ============================================================
-- Sheppard V3 — Universal Domain Authority Foundry Schema
--
-- Enforces strict canonical ownership.
-- Postgres owns identity, structure, lineage, and truth.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- ────────────────────────────────────────────────────────────
-- SCHEMAS
-- ────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS config;
CREATE SCHEMA IF NOT EXISTS mission;
CREATE SCHEMA IF NOT EXISTS corpus;
CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE SCHEMA IF NOT EXISTS authority;
CREATE SCHEMA IF NOT EXISTS application;

-- ────────────────────────────────────────────────────────────
-- UPDATED_AT TRIGGER
-- ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ════════════════════════════════════════════════════════════
-- 1. CONFIG
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS config.domain_profiles (
    profile_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain_type TEXT NOT NULL,
    description TEXT NOT NULL,
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_domain_profiles_domain_type ON config.domain_profiles(domain_type);

CREATE TRIGGER trg_domain_profiles_updated_at
BEFORE UPDATE ON config.domain_profiles FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ════════════════════════════════════════════════════════════
-- 2. MISSION
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS mission.research_missions (
    mission_id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    domain_profile_id TEXT NOT NULL REFERENCES config.domain_profiles(profile_id),
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    status TEXT NOT NULL,
    depth_target TEXT,
    budget_bytes BIGINT NOT NULL DEFAULT 0,
    bytes_ingested BIGINT NOT NULL DEFAULT 0,
    source_count INTEGER NOT NULL DEFAULT 0,
    stop_reason TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_research_missions_topic_id ON mission.research_missions(topic_id);
CREATE INDEX IF NOT EXISTS idx_research_missions_status ON mission.research_missions(status);

CREATE TRIGGER trg_research_missions_updated_at
BEFORE UPDATE ON mission.research_missions FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS mission.mission_events (
    event_id BIGSERIAL PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES mission.research_missions(mission_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mission_events_mission_id_created_at ON mission.mission_events(mission_id, created_at DESC);

CREATE TABLE IF NOT EXISTS mission.mission_nodes (
    node_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES mission.research_missions(mission_id) ON DELETE CASCADE,
    parent_node_id TEXT REFERENCES mission.mission_nodes(node_id) ON DELETE SET NULL,
    label TEXT NOT NULL,
    concept_form TEXT NOT NULL,
    surface_forms_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    artifact_forms_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    adjacency_forms_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL,
    priority NUMERIC(8,4) NOT NULL DEFAULT 0,
    coverage_score NUMERIC(8,4),
    gain_score NUMERIC(8,4),
    failure_signature TEXT,
    notes_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    exhausted_modes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mission_nodes_mission_id ON mission.mission_nodes(mission_id);
CREATE INDEX IF NOT EXISTS idx_mission_nodes_status ON mission.mission_nodes(status);

CREATE TRIGGER trg_mission_nodes_updated_at
BEFORE UPDATE ON mission.mission_nodes FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS mission.mission_mode_runs (
    mode_run_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES mission.research_missions(mission_id) ON DELETE CASCADE,
    node_id TEXT NOT NULL REFERENCES mission.mission_nodes(node_id) ON DELETE CASCADE,
    mode_name TEXT NOT NULL,
    status TEXT NOT NULL,
    budget_spent_bytes BIGINT NOT NULL DEFAULT 0,
    query_count INTEGER NOT NULL DEFAULT 0,
    result_count INTEGER NOT NULL DEFAULT 0,
    accepted_source_count INTEGER NOT NULL DEFAULT 0,
    gain_delta NUMERIC(8,4),
    stop_reason TEXT,
    error_class TEXT,
    error_detail TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_mode_runs_mission_id ON mission.mission_mode_runs(mission_id);
CREATE INDEX IF NOT EXISTS idx_mode_runs_node_id ON mission.mission_mode_runs(node_id);

CREATE TABLE IF NOT EXISTS mission.mission_frontier_snapshots (
    snapshot_id BIGSERIAL PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES mission.research_missions(mission_id) ON DELETE CASCADE,
    frontier_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_frontier_snapshots_mission_id_created_at ON mission.mission_frontier_snapshots(mission_id, created_at DESC);

-- ════════════════════════════════════════════════════════════
-- 3. CORPUS
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS corpus.sources (
    source_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES mission.research_missions(mission_id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL,
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    normalized_url_hash TEXT NOT NULL,
    domain TEXT,
    title TEXT,
    source_class TEXT NOT NULL,
    mime_type TEXT,
    language TEXT,
    trust_score NUMERIC(8,4),
    quality_score NUMERIC(8,4),
    canonical_text_ref TEXT,
    content_hash TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    captured_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sources_normalized_url_hash_mission ON corpus.sources(mission_id, normalized_url_hash);
CREATE INDEX IF NOT EXISTS idx_sources_topic_id ON corpus.sources(topic_id);
CREATE INDEX IF NOT EXISTS idx_sources_source_class ON corpus.sources(source_class);

CREATE TABLE IF NOT EXISTS corpus.source_fetches (
    fetch_id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES corpus.sources(source_id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL,
    http_status INTEGER,
    fetch_method TEXT,
    error_class TEXT,
    error_detail TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetch_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fetch_completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_source_fetches_source_id ON corpus.source_fetches(source_id);

CREATE TABLE IF NOT EXISTS corpus.text_refs (
    blob_id TEXT PRIMARY KEY,
    storage_uri TEXT,
    compression_codec TEXT,
    byte_size BIGINT,
    sha256 TEXT,
    inline_text TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (storage_uri IS NOT NULL OR inline_text IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS corpus.chunks (
    chunk_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES corpus.sources(source_id) ON DELETE CASCADE,
    mission_id TEXT NOT NULL REFERENCES mission.research_missions(mission_id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL,
    cluster_id TEXT,
    chunk_index INTEGER NOT NULL,
    start_offset INTEGER,
    end_offset INTEGER,
    token_count INTEGER,
    chunk_hash TEXT NOT NULL,
    text_ref TEXT REFERENCES corpus.text_refs(blob_id) ON DELETE SET NULL,
    inline_text TEXT,
    quality_score NUMERIC(8,4),
    boilerplate_score NUMERIC(8,4),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (text_ref IS NOT NULL OR inline_text IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_chunks_source_id ON corpus.chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_topic_id ON corpus.chunks(topic_id);
CREATE INDEX IF NOT EXISTS idx_chunks_cluster_id ON corpus.chunks(cluster_id);

CREATE TABLE IF NOT EXISTS corpus.chunk_features (
    chunk_id TEXT PRIMARY KEY REFERENCES corpus.chunks(chunk_id) ON DELETE CASCADE,
    feature_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS corpus.clusters (
    cluster_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES mission.research_missions(mission_id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL,
    label TEXT,
    representative_chunk_id TEXT REFERENCES corpus.chunks(chunk_id) ON DELETE SET NULL,
    member_count INTEGER NOT NULL DEFAULT 0,
    internal_diversity NUMERIC(8,4),
    novelty_score NUMERIC(8,4),
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clusters_mission_id ON corpus.clusters(mission_id);
CREATE INDEX IF NOT EXISTS idx_clusters_topic_id ON corpus.clusters(topic_id);

CREATE TABLE IF NOT EXISTS corpus.cluster_members (
    cluster_id TEXT NOT NULL REFERENCES corpus.clusters(cluster_id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL REFERENCES corpus.chunks(chunk_id) ON DELETE CASCADE,
    distance_to_rep NUMERIC(12,8),
    is_representative BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (cluster_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_members_chunk_id ON corpus.cluster_members(chunk_id);

CREATE TABLE IF NOT EXISTS corpus.cluster_differentials (
    cluster_id TEXT PRIMARY KEY REFERENCES corpus.clusters(cluster_id) ON DELETE CASCADE,
    differential_text_ref TEXT REFERENCES corpus.text_refs(blob_id) ON DELETE SET NULL,
    differential_status TEXT NOT NULL DEFAULT 'pending',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_cluster_differentials_updated_at
BEFORE UPDATE ON corpus.cluster_differentials FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ════════════════════════════════════════════════════════════
-- 4. KNOWLEDGE
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS knowledge.knowledge_atoms (
    atom_id TEXT PRIMARY KEY,
    authority_record_id TEXT,
    mission_id TEXT,
    topic_id TEXT NOT NULL,
    domain_profile_id TEXT NOT NULL REFERENCES config.domain_profiles(profile_id),
    atom_type TEXT NOT NULL,
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    summary TEXT,
    confidence NUMERIC(8,4),
    importance NUMERIC(8,4),
    novelty NUMERIC(8,4),
    stability TEXT,
    scope_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    qualifiers_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    lineage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_topic_id ON knowledge.knowledge_atoms(topic_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_authority_record_id ON knowledge.knowledge_atoms(authority_record_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_atom_type ON knowledge.knowledge_atoms(atom_type);

CREATE TRIGGER trg_knowledge_atoms_updated_at
BEFORE UPDATE ON knowledge.knowledge_atoms FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS knowledge.atom_evidence (
    atom_id TEXT NOT NULL REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES corpus.sources(source_id) ON DELETE CASCADE,
    chunk_id TEXT REFERENCES corpus.chunks(chunk_id) ON DELETE SET NULL,
    evidence_strength NUMERIC(8,4),
    supports_statement BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (atom_id, source_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_atom_evidence_source_id ON knowledge.atom_evidence(source_id);

CREATE TABLE IF NOT EXISTS knowledge.atom_relationships (
    atom_id TEXT NOT NULL REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE CASCADE,
    related_atom_id TEXT NOT NULL REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (atom_id, related_atom_id, relation_type)
);

CREATE TABLE IF NOT EXISTS knowledge.atom_entities (
    atom_id TEXT NOT NULL REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE CASCADE,
    entity_name TEXT NOT NULL,
    entity_type TEXT,
    PRIMARY KEY (atom_id, entity_name)
);

CREATE TABLE IF NOT EXISTS knowledge.atom_usage_stats (
    atom_id TEXT PRIMARY KEY REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE CASCADE,
    retrieval_count BIGINT NOT NULL DEFAULT 0,
    citation_count BIGINT NOT NULL DEFAULT 0,
    last_used_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS knowledge.contradiction_sets (
    contradiction_set_id TEXT PRIMARY KEY,
    authority_record_id TEXT,
    topic_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    resolution_status TEXT NOT NULL DEFAULT 'unresolved',
    confidence_split_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contradiction_sets_topic_id ON knowledge.contradiction_sets(topic_id);

CREATE TABLE IF NOT EXISTS knowledge.contradiction_members (
    contradiction_set_id TEXT NOT NULL REFERENCES knowledge.contradiction_sets(contradiction_set_id) ON DELETE CASCADE,
    atom_id TEXT NOT NULL REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE CASCADE,
    position_label TEXT,
    PRIMARY KEY (contradiction_set_id, atom_id)
);

CREATE TABLE IF NOT EXISTS knowledge.evidence_bundles (
    bundle_id TEXT PRIMARY KEY,
    bundle_type TEXT NOT NULL,
    authority_record_id TEXT,
    topic_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    section_name TEXT,
    coverage_status_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    constraints_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    assembly_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_bundles_topic_id ON knowledge.evidence_bundles(topic_id);

CREATE TABLE IF NOT EXISTS knowledge.bundle_atoms (
    bundle_id TEXT NOT NULL REFERENCES knowledge.evidence_bundles(bundle_id) ON DELETE CASCADE,
    atom_id TEXT NOT NULL REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE CASCADE,
    role_bucket TEXT NOT NULL,
    position_index INTEGER,
    PRIMARY KEY (bundle_id, atom_id)
);

CREATE TABLE IF NOT EXISTS knowledge.bundle_sources (
    bundle_id TEXT NOT NULL REFERENCES knowledge.evidence_bundles(bundle_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES corpus.sources(source_id) ON DELETE CASCADE,
    PRIMARY KEY (bundle_id, source_id)
);

CREATE TABLE IF NOT EXISTS knowledge.bundle_excerpts (
    excerpt_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL REFERENCES knowledge.evidence_bundles(bundle_id) ON DELETE CASCADE,
    source_id TEXT REFERENCES corpus.sources(source_id) ON DELETE SET NULL,
    chunk_id TEXT REFERENCES corpus.chunks(chunk_id) ON DELETE SET NULL,
    text_ref TEXT REFERENCES corpus.text_refs(blob_id) ON DELETE SET NULL,
    inline_text TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (text_ref IS NOT NULL OR inline_text IS NOT NULL)
);

-- ════════════════════════════════════════════════════════════
-- 5. AUTHORITY
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS authority.authority_records (
    authority_record_id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    domain_profile_id TEXT NOT NULL REFERENCES config.domain_profiles(profile_id),
    title TEXT NOT NULL,
    canonical_title TEXT NOT NULL,
    scope_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    frontier_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    corpus_layer_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    atom_layer_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    synthesis_layer_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    advisory_layer_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    lineage_layer_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    reuse_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_authority_records_topic_id ON authority.authority_records(topic_id);
CREATE INDEX IF NOT EXISTS idx_authority_records_domain_profile_id ON authority.authority_records(domain_profile_id);

CREATE TRIGGER trg_authority_records_updated_at
BEFORE UPDATE ON authority.authority_records FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS authority.authority_core_atoms (
    authority_record_id TEXT NOT NULL REFERENCES authority.authority_records(authority_record_id) ON DELETE CASCADE,
    atom_id TEXT NOT NULL REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    reason TEXT,
    PRIMARY KEY (authority_record_id, atom_id)
);

CREATE TABLE IF NOT EXISTS authority.authority_related_records (
    authority_record_id TEXT NOT NULL REFERENCES authority.authority_records(authority_record_id) ON DELETE CASCADE,
    related_authority_record_id TEXT NOT NULL REFERENCES authority.authority_records(authority_record_id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    PRIMARY KEY (authority_record_id, related_authority_record_id, relation_type)
);

CREATE TABLE IF NOT EXISTS authority.authority_advisories (
    advisory_id BIGSERIAL PRIMARY KEY,
    authority_record_id TEXT NOT NULL REFERENCES authority.authority_records(authority_record_id) ON DELETE CASCADE,
    advisory_type TEXT NOT NULL,
    statement TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_authority_advisories_authority_record_id ON authority.authority_advisories(authority_record_id);

CREATE TABLE IF NOT EXISTS authority.authority_frontier_state (
    authority_record_id TEXT PRIMARY KEY REFERENCES authority.authority_records(authority_record_id) ON DELETE CASCADE,
    frontier_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS authority.authority_contradictions (
    authority_record_id TEXT NOT NULL REFERENCES authority.authority_records(authority_record_id) ON DELETE CASCADE,
    contradiction_set_id TEXT NOT NULL REFERENCES knowledge.contradiction_sets(contradiction_set_id) ON DELETE CASCADE,
    PRIMARY KEY (authority_record_id, contradiction_set_id)
);

CREATE TABLE IF NOT EXISTS authority.synthesis_artifacts (
    artifact_id TEXT PRIMARY KEY,
    authority_record_id TEXT NOT NULL REFERENCES authority.authority_records(authority_record_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    title TEXT NOT NULL,
    abstract TEXT,
    content_ref TEXT REFERENCES corpus.text_refs(blob_id) ON DELETE SET NULL,
    freshness_state TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_synthesis_artifacts_authority_record_id ON authority.synthesis_artifacts(authority_record_id);

CREATE TRIGGER trg_synthesis_artifacts_updated_at
BEFORE UPDATE ON authority.synthesis_artifacts FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE IF NOT EXISTS authority.synthesis_sections (
    artifact_id TEXT NOT NULL REFERENCES authority.synthesis_artifacts(artifact_id) ON DELETE CASCADE,
    section_name TEXT NOT NULL,
    section_order INTEGER NOT NULL,
    content_ref TEXT REFERENCES corpus.text_refs(blob_id) ON DELETE SET NULL,
    summary TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (artifact_id, section_name)
);

CREATE TABLE IF NOT EXISTS authority.synthesis_citations (
    citation_id BIGSERIAL PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES authority.synthesis_artifacts(artifact_id) ON DELETE CASCADE,
    section_name TEXT,
    atom_id TEXT REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE SET NULL,
    source_id TEXT REFERENCES corpus.sources(source_id) ON DELETE SET NULL,
    citation_label TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_synthesis_citations_artifact_id ON authority.synthesis_citations(artifact_id);

CREATE TABLE IF NOT EXISTS authority.synthesis_lineage (
    artifact_id TEXT PRIMARY KEY REFERENCES authority.synthesis_artifacts(artifact_id) ON DELETE CASCADE,
    lineage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ════════════════════════════════════════════════════════════
-- 6. APPLICATION
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS application.application_queries (
    application_query_id TEXT PRIMARY KEY,
    project_id TEXT,
    query_type TEXT NOT NULL,
    title TEXT NOT NULL,
    problem_statement TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_application_queries_project_id ON application.application_queries(project_id);

CREATE TABLE IF NOT EXISTS application.application_outputs (
    output_id BIGSERIAL PRIMARY KEY,
    application_query_id TEXT NOT NULL REFERENCES application.application_queries(application_query_id) ON DELETE CASCADE,
    output_type TEXT NOT NULL,
    content_ref TEXT REFERENCES corpus.text_refs(blob_id) ON DELETE SET NULL,
    inline_text TEXT,
    confidence NUMERIC(8,4),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (content_ref IS NOT NULL OR inline_text IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_application_outputs_query_id ON application.application_outputs(application_query_id);

CREATE TABLE IF NOT EXISTS application.application_evidence (
    evidence_id BIGSERIAL PRIMARY KEY,
    application_query_id TEXT NOT NULL REFERENCES application.application_queries(application_query_id) ON DELETE CASCADE,
    authority_record_id TEXT REFERENCES authority.authority_records(authority_record_id) ON DELETE SET NULL,
    atom_id TEXT REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE SET NULL,
    bundle_id TEXT REFERENCES knowledge.evidence_bundles(bundle_id) ON DELETE SET NULL,
    CONSTRAINT application_evidence_nonempty_binding
        CHECK (authority_record_id IS NOT NULL OR atom_id IS NOT NULL OR bundle_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS application.application_lineage (
    application_query_id TEXT PRIMARY KEY REFERENCES application.application_queries(application_query_id) ON DELETE CASCADE,
    lineage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
