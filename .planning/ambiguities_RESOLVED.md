# Ambiguity Resolution Summary

**Date**: 2025-03-27
**Status**: All 28 critical ambiguities resolved via architectural decisions
**See Also**: `phases/phase0_foundation/01-SYSTEM_INVARIANTS.md` for complete contracts

---

## Resolution Overview

| Ambiguity | Resolution | Owner Doc |
|-----------|------------|-----------|
| A.1 Schema existence | **Create new**: migrations for `research.missions`, `corpus.sources`, `corpus.atoms`, etc. | §3, D-1 |
| A.2 `self.adapter` in DistillationPipeline | **Define `CorpusAdapter` protocol** - only DB boundary | §4, E-4 |
| A.3 `KnowledgeAtom` fields | **Standardized** with 15 fields + evidence join table | §3, D-1 |
| A.4 `AdaptiveFrontier.run()` API | **Contract**: `AsyncIterator[ConceptTask]`, yields tasks only | §4, E-1 |
| A.5 Budget storage measurement | **Use persisted counters** in `ops.budget_events`, not in-memory | §6, B-1 |
| A.6 `Crawler` API | **Two-level**: `crawl_concept(task)` + `fetch_url(url)` | §4, E-2 |
| A.7 Condensation trigger | **Event-driven**: emit `CONDENSATION_REQUESTED`, enqueue job, avoid callback storms | §4, E-3 |
| A.8 Frontier exhaustion | **Stop policy**: no pending tasks + no high-yield discoveries + modes exhausted | §4, E-1 |
| A.9 `mission_id` scoping | **Primary isolation boundary**. ALL tables include `mission_id` with indexes | §2, §3 |
| A.10 `ArchivistIndex` capabilities | **Redefine** as read facade over Postgres+Chroma, mission-filtered queries | §4, E-5 |
| A.11 Old `run_research` report | **Refactor** into `ReportAssembler` consuming atoms, not raw crawl | §4 |
| A.12 Configuration options | **Layered typed config**: defaults → env → file → CLI overrides | §10 |
| A.13 Multi-mission coordination | **Per-mission data isolation**, shared infra (Redis, workers, models) | §2, I-2 |
| A.14 `CorpusAdapter` definition | **Protocol** with 7 methods (get_unprocessed_chunks, write_atoms, etc.) | §4, E-4 |
| A.15 LLM errors in query | **Graceful degradation**: retry → fallback to retrieval-only → never crash | §7, F-2 |
| A.16 Query latency <2s | **Achievable**: retrieval-first (sub-2s), synthesis capped (sub-5s) | §10 |
| A.17 Coverage estimation | **Heuristic blend**: concept completion % + evidence density + contradiction burden | §11 |
| A.18 Confidence scoring | **Evidence agreement score**: source count, diversity, specificity, contradictions | §11 |
| A.19 Freshness calculation | **Based on newest supporting source date**, weighted by domain decay | §11 |
| A.20 Index multi-mission | **Logical filter first**: `WHERE mission_id`, separate collections if scale demands | §4, E-5 |
| A.21 CLI structure | **Mission-centric**: `sheppard mission start/status/stop/report/query` | §9 |
| A.22 API timeouts | **Never block**: REST for control, WebSocket/SSE for events; stop returns 202 | §8 |
| A.23 Crawler error retries | **Typed policy**: timeout/5xx (3x), 429 (5x), 403 (1x), parse (1x) | §7, F-1 |
| A.24 Race conditions | **Guardrails**: DB unique constraints, Redis locks, idempotency keys | §8 |
| A.25 Ceiling overshoot | **Allow temporary buffer**, trigger aggressive condensation at hard threshold | §6 |
| A.26 Prune raw content | **Condense and tombstone**: keep metadata+evidence, compress or mark raw body | §4 |
| A.27 Firecrawl testing | **Three-lane**: unit (mocked), integration (firecrawl-local), soak (budgeted real) | §12 |
| A.28 ResearchSystem integration | **Composition root**: ResearchSystem wires all components via DI | §4 |
| A.29 REST vs WebSocket | **Both**: REST for control, WebSocket/SSE for mission events | §8 |
| A.30 Source summaries vs atoms | **Promote only atoms** to canonical; summaries optional for preview | §4 |

---

## Key Architectural Decisions

### 1. Triad Authority Model (Hard Rule)
```
Postgres = truth
Chroma = projection (rebuildable from Postgres)
Redis = motion (ephemeral)
```

### 2. Quarantine Principle
Active crawl artifacts are **quarantined** until:
- Distilled into atoms
- Evidence attached
- Status = `verified` or `promoted`

**Agent default queries** see only `canonical` visibility. Mission-local queries can see `mission_local`. Debug mode sees `quarantined`.

---

### 3. Lineage First
Every atom must preserve immutable evidence chain:
```
Atom → (evidence table) → RawChunk → Source → Mission
```
No deletion of lineage. Raw body may be tombstoned, but hashes and metadata preserved.

---

### 4. Mission Isolation
`mission_id` is the tenant boundary. All queries filtered by mission unless `cross_mission=True` explicitly requested.

---

### 5. Idempotency & Retries
All writes must be retry-safe. Use:
- DB unique constraints
- `ON CONFLICT` handling
- Atomic transactions
- Exponential backoff with jitter

---

## What This Unblocks

With these resolutions, we can now:

1. ✅ **Write the database migrations** (schema is fixed)
2. ✅ **Implement `CorpusAdapter`** with clear API
3. ✅ **Build `AdaptiveFrontier`** knowing output format (`ConceptTask`)
4. ✅ **Wire crawler → adapter → DB** with idempotent writes
5. ✅ **Implement distillation** with clear input (chunks) and output (atoms+evidence)
6. ✅ **Design `ArchivistIndex`** with retrieval filters by visibility/status
7. ✅ **Build `ResearchOrchestrator`** with unambiguous contracts
8. ✅ **Define API endpoints** knowing request/response shapes
9. ✅ **Write CLI** knowing command structure
10. ✅ **Create test fixtures** with correct data shapes

---

## Remaining Dependencies

These are **external** to implementation and must be provided:

- PostgreSQL 15+ running (with `CREATE EXTENSION IF NOT EXISTS "uuid-ossp"`)
- ChromaDB connection (single instance or per-mission?)
- Redis connection (for queues/locks)
- LLM provider configured (Ollama/OpenRouter)
- Firecrawl API key or local Firecrawl

---

## Next Action Items

**Immediate (Today)**:

1. Create SQL migration file: `migrations/V3.0.0__initial_schema.sql` with all tables above
2. Create typed config classes: `src/research/config.py` with all subsections
3. Write `ConceptTask` dataclass in `src/research/models.py`
4. Write `CorpusAdapter` protocol in `src/research/adapter.py`
5. Write `KnowledgeAtom` dataclass matching schema

**Week 1 (Phase 0 implementation)**:

6. Implement `AdaptiveFrontier` with state persistence to `ops.mission_state`
7. Implement `Crawler` with `crawl_concept()` and `fetch_url()`
8. Implement `DistillationPipeline` with adapter dependency
9. Implement `ArchivistIndex` with visibility filters
10. Write integration test: mission → frontier → (mock) crawl → distillation → query

**Week 2**:

11. Implement `ResearchOrchestrator` coordinating all components
12. Implement WebSocket event bus
13. Implement API endpoints (REST + WS)
14. Implement CLI commands
15. End-to-end test with real PostgreSQL + Chroma + Redis

---

## Moral of the Story

**28 ambiguities = 28 architectural decisions** that are now locked.

This is **exactly** what Phase 0 should deliver: **unambiguous contracts** so implementation can proceed without second-guessing.

The key invariants are:

1. **Postgres is truth** - never lose to Chroma
2. **Mission isolation** - `mission_id` everywhere
3. **Lineage permanence** - evidence chain unbreakable
4. **Quarantine until verified** - no raw crawl in agent queries
5. **Idempotency** - safe to retry any operation

With these, the implementation is **mechanically derivable**.

---

**Ready to implement**. Do you want me to start with:

A. **Database migrations** (create actual SQL file)?
B. **Type definitions** (`ConceptTask`, `KnowledgeAtom`, config classes)?
C. **CorpusAdapter protocol** (interface-first)?
D. **Full Phase 0 implementation** (create all foundation code)?
