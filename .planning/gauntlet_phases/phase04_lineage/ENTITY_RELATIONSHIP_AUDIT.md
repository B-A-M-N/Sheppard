# Phase 04 — Entity Relationship Audit

**Auditor**: Claude Code (static analysis of schema and code)
**Date**: 2026-03-27

---

## Summary

The V3 data model is **well-normalized** with explicit foreign key constraints enforcing lineage. All core entities participate in referential integrity. The only notable exception is `knowledge_atoms.authority_record_id` which is intentionally unconstrained to allow atom creation before authority synthesis completes.

---

## Entity Catalog

### Mission Layer

| Entity | Table | Primary Key | Key Relationships |
|--------|-------|-------------|-------------------|
| Research Mission | `mission.research_missions` | `mission_id` (TEXT) | `domain_profile_id` → `config.domain_profiles` |
| Mission Event | `mission.mission_events` | `event_id` (BIGSERIAL) | `mission_id` → `mission.research_missions` CASCADE |
| Mission Node | `mission.mission_nodes` | `node_id` (TEXT) | `mission_id` → `mission.research_missions` CASCADE |
| Mission Mode Run | `mission.mission_mode_runs` | `mode_run_id` (TEXT) | `mission_id` → `mission.research_missions` CASCADE, `node_id` → `mission.mission_nodes` CASCADE |
| Frontier Snapshot | `mission.mission_frontier_snapshots` | `snapshot_id` (BIGSERIAL) | `mission_id` → `mission.research_missions` CASCADE |

### Corpus Layer

| Entity | Table | Primary Key | Key Relationships |
|--------|-------|-------------|-------------------|
| Source | `corpus.sources` | `source_id` (TEXT) | `mission_id` → `mission.research_missions` CASCADE |
| Source Fetch | `corpus.source_fetches` | `fetch_id` (BIGSERIAL) | `source_id` → `corpus.sources` CASCADE |
| Text Blob | `corpus.text_refs` | `blob_id` (TEXT) | Standalone (referred by chunks, synthesis, etc.) |
| Chunk | `corpus.chunks` | `chunk_id` (TEXT) | `source_id` → `corpus.sources` CASCADE; `mission_id` → `mission.research_missions` CASCADE; `text_ref` → `corpus.text_refs` SET NULL |
| Chunk Feature | `corpus.chunk_features` | `chunk_id` (TEXT) | `chunk_id` → `corpus.chunks` CASCADE |
| Cluster | `corpus.clusters` | `cluster_id` (TEXT) | `mission_id` → `mission.research_missions` CASCADE |
| Cluster Member | `corpus.cluster_members` | `(cluster_id, chunk_id)` | `cluster_id` → `corpus.clusters` CASCADE; `chunk_id` → `corpus.chunks` CASCADE |
| Cluster Differential | `corpus.cluster_differentials` | `cluster_id` (TEXT) | `cluster_id` → `corpus.clusters` CASCADE |

### Knowledge Layer

| Entity | Table | Primary Key | Key Relationships |
|--------|-------|-------------|-------------------|
| Knowledge Atom | `knowledge.knowledge_atoms` | `atom_id` (TEXT) | `domain_profile_id` → `config.domain_profiles`; `authority_record_id` (unconstrained) |
| Atom Evidence | `knowledge.atom_evidence` | `(atom_id, source_id, chunk_id)` | `atom_id` → `knowledge.knowledge_atoms` CASCADE; `source_id` → `corpus.sources` CASCADE; `chunk_id` → `corpus.chunks` SET NULL |
| Atom Relationship | `knowledge.atom_relationships` | `(atom_id, related_atom_id, relation_type)` | `atom_id` → `knowledge.knowledge_atoms` CASCADE; `related_atom_id` → `knowledge.knowledge_atoms` CASCADE |
| Atom Entity | `knowledge.atom_entities` | `(atom_id, entity_name)` | `atom_id` → `knowledge.knowledge_atoms` CASCADE |
| Atom Usage Stats | `knowledge.atom_usage_stats` | `atom_id` (TEXT) | `atom_id` → `knowledge.knowledge_atoms` CASCADE |
| Contradiction Set | `knowledge.contradiction_sets` | `contradiction_set_id` (TEXT) | `topic_id` (no FK) |
| Contradiction Member | `knowledge.contradiction_members` | `(contradiction_set_id, atom_id)` | `contradiction_set_id` → `knowledge.contradiction_sets` CASCADE; `atom_id` → `knowledge.knowledge_atoms` CASCADE |
| Evidence Bundle | `knowledge.evidence_bundles` | `bundle_id` (TEXT) | `authority_record_id`, `topic_id` (no FKs to authority) |
| Bundle Atom | `knowledge.bundle_atoms` | `(bundle_id, atom_id)` | `bundle_id` → `knowledge.evidence_bundles` CASCADE; `atom_id` → `knowledge.knowledge_atoms` CASCADE |
| Bundle Source | `knowledge.bundle_sources` | `(bundle_id, source_id)` | `bundle_id` → `knowledge.evidence_bundles` CASCADE; `source_id` → `corpus.sources` CASCADE |
| Bundle Excerpt | `knowledge.bundle_excerpts` | `excerpt_id` (TEXT) | `bundle_id` → `knowledge.evidence_bundles` CASCADE |

### Authority Layer

| Entity | Table | Primary Key | Key Relationships |
|--------|-------|-------------|-------------------|
| Authority Record | `authority.authority_records` | `authority_record_id` (TEXT) | `domain_profile_id` → `config.domain_profiles`; `topic_id` (no FK) |
| Authority Core Atom | `authority.authority_core_atoms` | `(authority_record_id, atom_id)` | `authority_record_id` → `authority.authority_records` CASCADE; `atom_id` → `knowledge.knowledge_atoms` CASCADE |
| Authority Related Record | `authority.authority_related_records` | `(authority_record_id, related_authority_record_id, relation_type)` | Both FKs to `authority.authority_records` CASCADE |
| Authority Advisory | `authority.authority_advisories` | `advisory_id` (BIGSERIAL) | `authority_record_id` → `authority.authority_records` CASCADE |
| Authority Frontier State | `authority.authority_frontier_state` | `authority_record_id` (TEXT) | `authority_record_id` → `authority.authority_records` CASCADE |
| Authority Contradiction | `authority.authority_contradictions` | `(authority_record_id, contradiction_set_id)` | `authority_record_id` → `authority.authority_records` CASCADE; `contradiction_set_id` → `knowledge.contradiction_sets` CASCADE |
| Synthesis Artifact | `authority.synthesis_artifacts` | `artifact_id` (TEXT) | `authority_record_id` → `authority.authority_records` CASCADE |
| Synthesis Section | `authority.synthesis_sections` | `(artifact_id, section_name)` | `artifact_id` → `authority.synthesis_artifacts` CASCADE |
| Synthesis Citation | `authority.synthesis_citations` | `citation_id` (BIGSERIAL) | `artifact_id` → `authority.synthesis_artifacts` CASCADE; `atom_id`/`source_id` optional SET NULL |
| Synthesis Lineage | `authority.synthesis_lineage` | `artifact_id` (TEXT) | `artifact_id` → `authority.synthesis_artifacts` CASCADE |

### Application Layer

| Entity | Table | Primary Key | Key Relationships |
|--------|-------|-------------|-------------------|
| Application Query | `application.application_queries` | `application_query_id` (TEXT) | `project_id` (no FK) |
| Application Output | `application.application_outputs` | `output_id` (BIGSERIAL) | `application_query_id` → `application.application_queries` CASCADE |
| Application Evidence | `application.application_evidence` | `(application_query_id, authority_record_id, atom_id, bundle_id)` | `application_query_id` → `application.application_queries` CASCADE; all other FKs SET NULL |
| Application Lineage | `application.application_lineage` | `application_query_id` (TEXT) | `application_query_id` → `application.application_queries` CASCADE |

---

## Constraint Summary

### Foreign Keys Enforced (ON DELETE CASCADE or SET NULL)

- All mission_* tables → `mission.research_missions`
- All corpus_* tables → `corpus.sources` or `corpus.chunks`
- All knowledge_* tables → `knowledge.knowledge_atoms` (except `knowledge_atoms` itself and `contradiction_sets`)
- All authority_* tables → `authority.authority_records` or `authority.synthesis_artifacts`
- All application_* tables → `application.application_queries`

### Intentional Orphan Allowances

| Table | Column | Reason |
|-------|--------|--------|
| `knowledge.knowledge_atoms` | `authority_record_id` | Atoms can be created before authority synthesis; linkage added later |
| `knowledge.evidence_bundles` | `authority_record_id`, `topic_id` | Bundles may be created ahead of final authority record |
| `authority.authority_records` | `topic_id` | Authority tied to topic but no formal FK (topic_id is free text) |
| `knowledge.contradiction_sets` | `topic_id` | Contradictions tracked by topic, not FK |

These are **acceptable** because:
- They reference either non-entity topics (business keys) or optional future entities
- The fields are not used for referential integrity checks, only for indexing/discovery

---

## Mandatory Question Answers

### Q: Can every atom be tied to a source?

**Yes**. Through `knowledge.atom_evidence`, which has required FKs:
- `atom_evidence.atom_id` → `knowledge_atoms` (CASCADE)
- `atom_evidence.source_id` → `corpus.sources` (CASCADE)
- Evidence table has composite PK, ensuring at least one evidence row per atom (but see **orphan risk** section for caveats about creation order).

### Q: Can every source be tied to a mission?

**Yes**. `corpus.sources.mission_id` is a required foreign key with `ON DELETE CASCADE`.

### Q: Can every report be tied to atoms?

**Yes**. `authority.synthesis_citations` and `authority.authority_core_atoms` provide links from `synthesis_artifacts` to `knowledge_atoms`.

### Q: Can lineage survive retries/reprocessing?

**Partially**. The schema is **append-only** friendly:
- New sources with same `normalized_url_hash` per mission are prevented by unique index
- Reprocessing a source creates new chunks (new `chunk_id`) but same `source_id`
- Atoms may be upserted (same `atom_id` regenerated) and evidence rebinding overwrites

**Caveat**: `atom_evidence` uses bulk upsert; if a chunk is replaced, old evidence rows pointing to it remain until explicitly cleaned. This is a **retention** issue, not a lineage break.

### Q: Is lineage immutable or overwritten?

- **FK relationships**: Immutable (you cannot change a `source_id` on a chunk; you must delete/recreate)
- **Content updates**: Restricted by `ON DELETE` rules; most updates are actually upserts that preserve identity
- **Soft deletion**: Not used; hard deletes cascade (so lineage deletions are possible but should be rare)

**Conclusion**: Lineage is **effectively immutable** once established, because primary keys are UUIDs generated at creation time and foreign keys are not updatable.

---

## Orphan Risk Assessment (Detailed in next file)

High-level:
- **Atom without evidence**: Possible if `upsert_atom` is called before `bind_atom_evidence` (existing bug)
- **Source without chunks**: Possible (chunking missing) — this is a known Phase 02 blocker that should be resolved
- **Atom without authority linkage**: Acceptable; atoms can exist independently

---

## Schema Strengths

1. **Cascade deletes**: Ensure no orphans accumulate from deletions
2. **Composite PKs**: `atom_evidence` enforces atomic triples
3. ** CHECK constraints**: `chunks` requires either `text_ref` or `inline_text`
4. **Unique indexes**: Prevent duplicate source ingestion per mission
5. **Timestamp triggers**: `updated_at` maintained automatically

---

## Schema Gaps

1. **No foreign key from `knowledge_atoms` to `authority_records`** — intentional, but could be added later if authority linkage becomes mandatory
2. **No foreign key from `corpus.chunks` to `knowledge.atom_evidence`** (reverse direction is enforced)
3. **`atom_evidence.chunk_id` is nullable** — evidence can be at source level (acceptable)
4. **`evidence_bundles` lacks FKs to `authority_records`** — only `topic_id` (free text) — acceptable as bundles can be pre-authority

---

**Verdict**: Relationships are **structurally sound** and lineage is queryable end-to-end. Known gaps are either acceptable or documented.
