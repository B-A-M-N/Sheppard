# Sheppard V2 — Schema & Pipeline Delta Notes

## What changed from the first scaffold and why

---

### schema.sql — Major additions

**Session memory (`crawl_sessions`)**
Each /learn invocation now has its own session record that tracks the
full job config (query, ceiling, allowed source types, stop conditions)
plus execution stats and open gaps. This is the reproducibility layer —
you can re-run any session exactly or diff two sessions on the same topic.

**Novelty tracking (`novelty_scores`)**
Per-session rolling novelty scores, measured every N docs. When
rolling novelty drops below the configured floor for N consecutive
documents, the crawl stops early. Prevents collecting 8GB of
recycled blog posts on a well-covered topic.

**Level B: Typed knowledge atoms (`knowledge_atoms`)**
Replaces the old "one summary blob" approach. Every atomic statement
is typed (claim, definition, procedure, comparison, constraint,
open_question, disagreement, example, failure_mode, best_practice)
and must have at least one source link. This makes the system
queryable at the claim level, not just the document level.

**Atom-source links (`atom_source_links`)**
Explicit many-to-many table enforcing the provenance invariant.
Every atom has a source. No orphaned knowledge.

**Contradiction registry (`contradictions`)**
Contradictions are stored explicitly and never averaged away.
`is_contested` flag propagates back to individual atoms.
The `contested_knowledge` view exposes all unresolved contradictions
for display during reasoning.

**Source quality registry (`source_quality`)**
Per-domain trust scores, pre-seeded with academic whitelist.
Updated over time via meta_memory feedback. Feeds `trust_score`
on sources and bubbles up to atom confidence and re-ranking.

**Level C: Thematic syntheses (`thematic_syntheses`)**
Named artifact types (failure_modes, best_practices, design_tradeoffs,
open_problems, topic_summary, concept_map). Each synthesis links back
to its source atoms. Searchable as a distinct ChromaDB collection.

**Level D: Advisory briefs (`advisory_briefs`)**
The <1% layer. Structured JSON fields:
- what_matters
- what_is_contested
- what_is_likely_true
- what_needs_testing
- how_applies_to_projects
- open_questions

**Project artifacts (`project_artifacts`)**
Projects now have a proper artifact graph: files, modules, interfaces,
design_docs, todos, arch_decisions, test_failures, benchmarks, tickets.

**Project-knowledge links (`project_knowledge_links`)**
Cross-links typed by: applies | implements | gaps | risks |
opportunities | contradicts | validates. This is where
"external failure mode ↔ internal risk point" gets stored.

**Meta-memory (`meta_memory`)**
Tracks source reliability, synthesis fidelity, retrieval quality,
prompt effectiveness over time. Feeds system self-improvement.
The `knowledge_promotion_log` records when knowledge moves between
session → domain → advisory tiers.

**Useful views**
- `topic_health` — storage ratios + unresolved contradiction count
- `session_novelty_trend` — novelty decay over a crawl session
- `contested_knowledge` — all unresolved contradictions
- `project_knowledge_gaps` — project artifacts with no linked knowledge

---

### condensation/pipeline.py — Refactored to DistillationPipeline

**Renamed**: CondensationPipeline → DistillationPipeline
The name change is intentional — it signals the architectural shift
from compression to multi-level knowledge refinement.

**Old behavior**: One 10% summary blob per source batch  
**New behavior**: Four artifact tiers with distinct retrieval roles

Phase map:
```
LOW  (70%)  → dedup + Level B atoms only
HIGH (85%)  → dedup + Level B + Level C thematic synthesis
CRITICAL (95%) → dedup + B + C + Level D advisory brief + prune raw
```

Key changes:
- Atom extraction uses labeled sources with [S1] citation keys —
  the LLM can produce atoms that point to specific sources
- Contradiction detection runs as a dedicated phase after extraction
- Thematic synthesis is grouped by atom_type (failure_mode → failure_modes
  synthesis, best_practice → best_practices synthesis, etc.)
- Advisory brief is structured JSON with named fields, not prose
- Meta-memory records fidelity estimate after every pass
- Novelty scoring exposed as a public method for the crawler to call

---

### reasoning/retriever.py — 4-stage with role-based assembly

**Old Stage order**: fan-out 4 strategies in parallel → top-K merge  
**New Stage order**: lexical → (semantic + structural in parallel) → rerank → role-fill

**Stage 1 (Lexical)** is new. Runs BEFORE vector search.
Extracts exact-match terms from the query (CamelCase, ALL_CAPS,
hyphenated-terms, quoted phrases, version strings) and does
a Postgres trgm full-text search. Catches things vector search misses:
- "SOLLOL" (project name)
- "mxbai-embed-large" (specific model)
- "RecursiveCTE" (technical term)
- error strings like "CUDA out of memory"

**Stage 4 (Rerank)** composite score uses 6 signals:
- relevance_score (0.35 weight) — query match quality
- trust_score (0.20) — source domain authority
- recency_factor (0.10) — decays with age
- tech_density (0.15) — technical content proxy
- project_proximity (0.20) — project-linked items upweighted

**Role-based assembly** fills named slots:
```
2-3 definitions      → item_type = "definition" or concept graph
3-5 evidence         → highest composite score from remainder
2 contradictions     → is_contradiction = True
2 project artifacts  → project_proximity > 0
1-2 unresolved       → item_type = "open_question" or "open_problems"
```

Why this matters: a pure top-K retriever might return 12 evidence items
with zero definitions and zero contradictions. The LLM then hallucinates
definitions and never acknowledges uncertainty. Role-based assembly
forces the context to cover all the epistemic bases.

---

## Memory method additions needed in manager.py

These are new methods the revised pipeline and retriever call that
weren't in the original manager.py spec:

```python
# Level B
store_atom(topic_id, session_id, atom_type, content, source_ids,
           citation_keys, verbatim_excerpt, confidence,
           is_contested, is_time_sensitive) → atom_id

update_atom_chroma_id(atom_id, chroma_chunk_id)
mark_atom_contested(atom_id)

store_contradiction(topic_id, atom_a_id, atom_b_id, description)
search_contradictions(query_text, topic_id, limit) → list

# Level C
store_synthesis(topic_id, session_id, synthesis_type, title,
                content, source_atom_ids, source_chunk_ids) → synthesis_id
update_synthesis_chroma_id(synthesis_id, chroma_chunk_id)

# Level D
store_advisory_brief(topic_id, session_id, what_matters,
                     what_is_contested, what_is_likely_true,
                     what_needs_testing, how_applies_to_projects,
                     open_questions, source_synthesis_ids) → brief_id

# Session + novelty
create_session(topic_id, seed_query, ceiling_bytes, ...) → session_id
record_novelty_score(session_id, topic_id, doc_sequence, rolling_novelty)
update_session_stop_reason(session_id, stop_reason)

# Meta-memory
record_meta_memory(entity_type, entity_id, observation_type,
                   score, notes, topic_id, session_id)

# Distillation log (replaces log_condensation)
log_distillation(report: DistillationReport)

# Retrieval
lexical_search_atoms(terms, topic_id, limit) → list
```
