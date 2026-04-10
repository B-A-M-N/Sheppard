# Project Roadmap

**Current Milestone:** v1.3 — Persistence, Reliability & Extraction Quality
**Archived Milestones:**
- v1.0 — Truth Contract Implementation (✅ Shipped 2026-03-30)
- v1.1 — Performance & Observability (✅ Shipped 2026-03-31)
- v1.2 — Derived Insight & Report Excellence Layer (✅ Shipped 2026-04-01)

---

## v1.2 — Derived Insight & Report Excellence Layer (Archived)

All phase details archived in `.planning/milestones/v1.2-ROADMAP.md`.

<details>
<summary>Expand for brief status</summary>

- 12-A Derived Claim Engine ✅
- 12-B Dual Validator Extension ✅
- 12-C Evidence Graph / Claim Graph ✅
- 12-D Evidence-Aware Section Planner ✅
- 12-E Multi-Pass Composition Pipeline ✅
- 12-F Longform Verifier ✅

**Summary:** v1.2 delivers advanced analytical reasoning with deterministic derived claims, evidence graph clustering, multil-pass synthesis, and 7-gate longform verification.

</details>

## v1.1 — Performance & Observability (Archived)

All phase details archived in `.planning/milestones/v1.1-ROADMAP.md`.

<details>
<summary>Expand for brief status</summary>

- 12-01 Benchmark suite ✅
- 12-02 Retrieval optimization ✅
- 12-02.1 Latency diagnosis ✅
- 12-02.2 Batch queries ✅
- 12-03 Synthesis throughput 🟡 (partial: deployment-bound)
- 12-04 Observability ✅
- 12-05 Contradictions V3 ✅
- 12-06 High-evidence E2E ✅
- 12-07 Ranking ✅

**Known limitation:** PERF-02 (throughput target) not met due to single-endpoint inference serialization; architecture ready for multi-endpoint scaling.

</details>

## v1.0 — Truth Contract Implementation (Archived)

All phase details archived in `.planning/milestones/v1.0-ROADMAP.md`.

<details>
<summary>Expand for brief status</summary>

- Phase 10 Interactive Truth-Grounded Retrieval ✅
- Phase 11 Synthesis Truth Contract ✅
- Phase 11.1 Remediation ✅

**Verdict:** PASS. End-to-end truth guarantees enforced.

</details>

---

## v1.3 — Persistence, Reliability & Extraction Quality

## Phases

- [ ] **Phase 13: Foundation** — Audit table, transaction safety, field standardization, source status tracking
- [ ] **Phase 14: Pipeline Integrity** — Idempotency, state machine, embedding versioning, deferred writes, dead-letter queue, metrics
- [ ] **Phase 15: Terminal UX** — Log redirection, Redis pub/sub, compact status bar
- [ ] **Phase 16: Extraction Quality** — Granularity hints, token-based chunking, computed confidence
- [ ] **Phase 17: Consolidation** — Golden Atoms, contradiction detection and resolution
- [ ] **Phase 18: JSON Reliability** — Firecrawl parse preference, constrained decoding, Pydantic validation, retry loop, backpressure

---

## Phase Details

### Phase 13: Foundation
**Goal**: Establish durable pipeline audit trail, transaction-safe writes, and standardized data model — eliminating silent data loss paths.
**Depends on**: Nothing (first v1.3 phase)
**Requirements**: PERSIST-01, PERSIST-03, PERSIST-04, PERSIST-05
**Success Criteria** (what must be TRUE):
  1. Every extraction/condensation run leaves a `pipeline_runs` audit row with start time, end time, source count, and result count
  2. Multi-table operations (store_source, store_atom, store_synthesis, condensation batch, scout multi-table) either fully commit or fully roll back — no partial writes on failure
  3. Codebase uses only `text` field on KnowledgeUnit — no dual-key `text`/`content` fallback anywhere in distillation_pipeline.py or condensation/pipeline.py
  4. Filtered sources show explicit status (`filtered_out`) with categorized failure reasons (too short, failed quality, duplicate, semantic drift)
**Plans**: TBD

### Phase 14: Pipeline Integrity
**Goal**: Make every pipeline stage idempotent, observable, and failure-resilient — no data silently lost.
**Depends on**: Phase 13 (needs audit table schema, transactions, field standardization)
**Requirements**: PERSIST-06, PERSIST-07, PERSIST-08, PERSIST-09, PERSIST-02, OBS-01
**Success Criteria** (what must be TRUE):
  1. Re-running any pipeline stage with the same input produces identical results via deterministic `run_id` and unique constraint `(source_id, stage, chunk_hash)` — no duplicate atoms
  2. Source status progresses through defined state machine: `pending → scraped → extracted → filtered_out → consolidated → finalized | failed`
  3. All Chroma vectors carry `embedding_model` and `embedding_version` metadata; system can identify vectors needing rebuild when model changes
  4. Postgres source/atom writes succeed independently of Chroma availability — Chroma insert is retried asynchronously; Postgres remains single source of truth
  5. Failed pipeline runs record structured error details (message, traceback, stage) in dead-letter table — never return silent `[]`
  6. Pipeline metrics (atoms/sec, extraction success rate, retry count per source, avg chunk size, contradiction rate) emitted via structured JSON logging
**Plans**: TBD

### Phase 15: Terminal UX
**Goal**: Eliminate terminal flooding from background tasks and provide structured status visibility.
**Depends on**: Nothing (independent of PERSIST/EXTRACT work)
**Requirements**: TUI-01, TUI-02, TUI-03
**Success Criteria** (what must be TRUE):
  1. Background tasks (vampire loops, AdaptiveFrontier, distillation pipeline, budget monitor) produce zero output to terminal — all use `logger.info()` instead of `console.print()`
  2. Redis pub/sub channel `sheppard:status` broadcasts structured events with component, event type, summary metrics, and timestamp
  3. Chat input area remains clean during background processing — status bar renders compactly without overwriting user input
**Plans**: TBD

### Phase 16: Extraction Quality
**Goal**: Replace truncation-based extraction with controlled, chunked, granularity-aware extraction with measurable confidence.
**Depends on**: Phase 14 (EXTRACT-02 chunking requires PERSIST-06 idempotency for safe re-runs)
**Requirements**: EXTRACT-01, EXTRACT-02, EXTRACT-05
**Success Criteria** (what must be TRUE):
  1. Extraction prompt produces targeted 5-15 atoms with explicit granularity rules (one finding per atom, include metrics, no combining, no splitting)
  2. Sources exceeding ~3500 tokens are chunked with 200-token overlap and cross-chunk deduplication — no 4000-char truncation
  3. Atom confidence computed from measurable signals (source reliability × 0.2, corroboration count × 0.05 up to 0.2, quality score × 0.1) — no LLM self-assessed confidence
**Plans**: TBD

### Phase 17: Consolidation
**Goal**: Complete atom lifecycle by merging duplicates into Golden Atoms and resolving contradictory claims.
**Depends on**: Phase 16 (needs EXTRACT-01 granularity hints for meaningful clustering)
**Requirements**: EXTRACT-03, EXTRACT-04
**Success Criteria** (what must be TRUE):
  1. `consolidate_atoms()` merges similar atoms (cosine similarity ≥ 0.85) into Golden Atoms with combined `source_ids` — originals marked obsolete
  2. `resolve_contradictions()` detects embedding-similar atoms with confidence divergence, verifies via LLM, adjudicates by source reliability — losing atoms marked obsolete with reason
**Plans**: TBD

### Phase 18: JSON Reliability & Infrastructure
**Goal**: Guarantee structurally valid JSON from 8B models and enforce system-wide concurrency limits.
**Depends on**: Nothing (independent; can run in parallel with earlier phases)
**Requirements**: FIRE-01, FIRE-02, FIRE-03, FIRE-04, INFRA-01
**Success Criteria** (what must be TRUE):
  1. Firecrawl uses `scrape` with `formats: ['markdown']` instead of `/v2/extract` — no internal schema wrapping breaking 8B models
  2. All extraction LLM calls use Ollama `format` parameter with JSON schema — structural validity guaranteed at generation time
  3. Post-generation Pydantic validation strips markdown fences, parses JSON, validates against `KnowledgeAtom` schema, rejects unknown fields
  4. Failed JSON parsing triggers retry loop (max 3) with validation error injected into retry prompt, cooldown between attempts, dead-letter on final failure
  5. System enforces concurrency limits: max concurrent Firecrawl jobs, max extraction workers, queue depth monitoring with warning thresholds
**Plans**: TBD

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 13. Foundation | 0/N | Not started | - |
| 14. Pipeline Integrity | 0/N | Not started | - |
| 15. Terminal UX | 0/N | Not started | - |
| 16. Extraction Quality | 0/N | Not started | - |
| 17. Consolidation | 0/N | Not started | - |
| 18. JSON Reliability & Infrastructure | 0/N | Not started | - |

---

## Coverage

All 23 v1.3 requirements mapped to exactly one phase:

| Requirement | Phase | Category |
|-------------|-------|----------|
| PERSIST-01 | 13 | Foundation |
| PERSIST-03 | 13 | Foundation |
| PERSIST-04 | 13 | Foundation |
| PERSIST-05 | 13 | Foundation |
| PERSIST-06 | 14 | Pipeline Integrity |
| PERSIST-07 | 14 | Pipeline Integrity |
| PERSIST-08 | 14 | Pipeline Integrity |
| PERSIST-09 | 14 | Pipeline Integrity |
| PERSIST-02 | 14 | Pipeline Integrity |
| OBS-01 | 14 | Pipeline Integrity |
| TUI-01 | 15 | Terminal UX |
| TUI-02 | 15 | Terminal UX |
| TUI-03 | 15 | Terminal UX |
| EXTRACT-01 | 16 | Extraction Quality |
| EXTRACT-02 | 16 | Extraction Quality |
| EXTRACT-05 | 16 | Extraction Quality |
| EXTRACT-03 | 17 | Consolidation |
| EXTRACT-04 | 17 | Consolidation |
| FIRE-01 | 18 | JSON Reliability & Infrastructure |
| FIRE-02 | 18 | JSON Reliability & Infrastructure |
| FIRE-03 | 18 | JSON Reliability & Infrastructure |
| FIRE-04 | 18 | JSON Reliability & Infrastructure |
| INFRA-01 | 18 | JSON Reliability & Infrastructure |

**Coverage: 23/23 requirements mapped ✓**
**No orphaned requirements.**
**No duplicated requirements.**

---

## Dependency Graph

```
Phase 13 (Foundation)
  └── PERSIST-01, PERSIST-03 (prerequisites for all other PERSIST)
        │
        ▼
Phase 14 (Pipeline Integrity)
  └── PERSIST-06 (idempotency) required by EXTRACT-02
        │
        ▼
Phase 16 (Extraction Quality)
  └── EXTRACT-01 (granularity hints) required by EXTRACT-03
        │
        ▼
Phase 17 (Consolidation)

Phase 15 (Terminal UX) — independent, can run in parallel

Phase 18 (JSON Reliability & Infrastructure) — independent, can run in parallel
```

---

## Future Work

*Next milestone to be defined via `/gsd:new-milestone`.*

**Legend**: ✅ Completed, ⬜ Pending, 🔄 In Progress

## Notes

- All gaps from Phase 06-01 audit have been closed.
- Database migration pending for `exhausted_modes_json` column.
- v1.1 shipped with known limitation: PERF-02 throughput target not met due to deployment constraint (single-endpoint inference). Architecture ready for scaling in v1.2.
- v1.2 shipped with complete derived insight pipeline; LongformVerifier integration ready for Pass 5 plug-in.
