# Milestone v1.1 — Performance & Observability — Requirements

**Objective:** Optimize performance, add observability, and upgrade contradiction handling without breaking any v1.0 truth contract invariants.

**Non-Negotiable Guardrails:**
- No changes may weaken Phase 10/11 invariants.
- All optimizations must pass existing validation suite unchanged.
- Truth contract remains enforced end-to-end.

---

## Focus Areas & Requirements

### 1. Performance Optimization

**Goal:** Reduce latency and increase throughput of retrieval and synthesis pipelines.

**Requirements:**
- [x] **PERF-01:** Retrieval query latency P95 < 200ms (currently baseline unknown, must measure first)
- **PERF-02:** Synthesis throughput (sections/min) improved by ≥20% via batching/parallelization where safe
- **PERF-03:** Chunk/atom storage efficiency: minimize redundant embeddings; deduplicate identical chunks across sources
- **PERF-04:** Async bounds tuning: connection pool sizes, worker concurrency limits documented

**Acceptance:** Benchmark suite added (`scripts/benchmark_*.py`) showing before/after metrics; no regression in truth contract tests.

---

### 2. Observability & Debugging

**Goal:** Provide full visibility into mission lifecycle, retrieval quality, and synthesis outcomes.

**Requirements:**
- **OBS-01:** Structured metrics (Prometheus/Statsd format or JSON logs) for:
  - Retrieval: hit rate, result count, latency by mission_id
  - Synthesis: sections generated, validator rejections (broken down by reason), citation counts per section
  - Storage: DB query latencies, cache hit rates
- **OBS-02:** Distributed tracing: each mission generates trace IDs that flow through:
  - Frontier → Acquisition → Condensation → Retrieval → Synthesis → Storage
  - Each major step logs span start/end with parent context
- **OBS-03:** Debug surfaces:
  - `GET /api/v1/missions/{id}/timeline` returns timeline of steps with durations
  - `GET /api/v1/missions/{id}/retrieval` returns atoms retrieved per section with citation keys
  - `GET /api/v1/metrics` exposes real-time metrics
- **OBS-04:** Dashboard (Grafana or simple HTML) showing:
  - Active missions and their current phase
  - Error rates by component
  - Latency heatmaps

**Acceptance:** Observability pipeline functional; can reconstruct full mission execution path post-hoc.

---

### 3. High-Evidence End-to-End Coverage

**Goal:** Exercise the full synthesis path with real atoms (not just NO_DISCOVERY) to validate the complete truth chain.

**Requirements:**
- **E2E-01:** Integration test that runs: mission → frontier → ingestion → extraction → retrieval → synthesis → report persistence
- **E2E-02:** Test verifies:
  - At least one atom retrieved per section on average
  - All section citations match `atom_ids_used` stored in DB
  - Report passes validator when re-checked
  - `atom_ids_used` array matches `synthesis_citations` rows
- **E2E-03:** Test runs in CI on a small, deterministic topic with controlled corpus

**Acceptance:** `npm test` (or equivalent) includes this full-path E2E; it passes consistently.

---

### 4. Contradiction System Upgrade

**Goal:** Replace legacy `memory.get_unresolved_contradictions` with V3-native query against stored contradictions.

**Requirements:**
- **CONTR-01:** Remove dependency on `memory` system for contradictions; contradiction retrieval goes through `V3Retriever` or direct DB query against `knowledge.contradictions` table
- **CONTR-02:** Contradictions properly attributed to source atoms (FK to `knowledge.knowledge_atoms`)
- **CONTR-03:** Synthesis includes contradictions when relevant to section (via `target_evidence_roles` containing "contradictions" or similar)
- **CONTR-04:** Validator recognizes contradiction citations as valid support (no special treatment needed if they're just atoms)

**Acceptance:** Contradiction retrieval no longer calls `memory.get_unresolved_contradictions`; all contradictions come from V3 store.

---

### 5. Ranking Improvements (Constraint-Safe)

**Goal:** Improve atom ordering beyond simple lexical sort while preserving determinism and fairness.

**Requirements:**
- **RANK-01:** Introduce relevance scoring (e.g., cosine similarity + recency + source authority) within retrieval limit
- **RANK-02:** Must remain deterministic: same query + same corpus + same seed → identical ordering
- **RANK-03:** No hard filtering: all retrieved atoms (up to limit) still returned; just reordered
- **RANK-04:** Scoring parameters configurable via `RetrievalQuery` options (default preserves current behavior)

**Acceptance:** Retrieval tests updated to allow ordering variation within deterministic seed; no truth contract violations.

---

## Out of Scope (Deferred)

- Changes to truth contract itself (already finalized in v1.0)
- Modifications to validator logic
- Alterations to `mission_id` propagation or `atom_ids_used` storage
- Major refactors outside stated focus areas

---

## Success Criteria

- All existing tests pass (no regressions)
- New benchmarks demonstrate performance gains (or at least no degradation >5%)
- Observability data available for at least one full mission run
- High-evidence E2E test included and green
- Contradiction system fully V3-native
- Code review confirms no weakening of invariants

---

## Notes

This milestone builds on the **provably correct** foundation of v1.0. Treat the truth contract as a fixed substrate; optimize around it.
