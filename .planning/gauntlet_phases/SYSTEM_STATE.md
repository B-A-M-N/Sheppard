# Sheppard V3 — System State Declaration

**Date:** 2025-03-27
**Phase:** 01 — Ground-Truth Inventory Complete

---

## Executive Summary

> **Current State:** V2 Operational Core
> **Target State (as documented):** V3 Triad Architecture

**Conclusion:** There is a **system identity mismatch**. The codebase is a V2 system with V3 aspirational artifacts (schema files, dead code, documentation). The V3 architecture described in README is **not implemented**.

---

## What Is Actually Real (Executable)

### Storage Stack (Working)

- **Redis** — queue, locks, cache (localhost:6379)
- **ChromaDB** — vector storage (`chroma_storage/` directory)
- **In-memory / file-based** — some content in `data/`, `corpus.text_refs` likely used

### Core Pipeline (Monolithic)

- `ResearchSystem.research_topic()` — single method orchestrates discovery → crawl → extraction → storage
- Located in: `src/research/base_system.py` (likely)
- Not decomposed into frontier/crawler/smelter as claimed

### Commands (Actual)

The interactive console (`main.py`) exposes:

- `/research` — start research mission (not `/learn`)
- `/memory` — memory operations (not `/query`)
- `/status` — system status (exists as claimed)
- Others: `/browse`, `/settings`, `/preferences`, `/project`, `/clear`, `/save`, `/exit`

**Missing from README:**
- `/learn`
- `/query`
- `/report`
- `/nudge`

### Workers (Basic)

- `scout_worker.py` — single worker type, pulls from Redis `queue:scraping`
- No advanced swarm coordination, no node identity, no priority queues
- Parallelism via multiple processes (manual deployment)

---

## What Is Not Real (Aspirational/Dead)

### Infrastructure (Missing)

- **PostgreSQL** — claimed as "The Truth" but not integrated. V3 schema files exist (`src/memory/schema_v3.sql`) but tables are **not created** and **no code writes to them**.
- **Triad enforcement** — only 2/3 stores active (Redis+Chroma). Triad is a documentation concept, not runtime reality.

### Architecture Components (Unconnected)

- `src/core/sheppard/` — appears to be V3 module stubs (frontier, orchestrator, adapter) — **unused** by main app
- `src/core/memory/storage/` — V3 adapter protocol and implementations (Postgres, Chroma, Redis) — **not wired**
- `pipeline.py` in `src/research/` — separate distillation pipeline — **not called**
- `mission.*` tables, `knowledge.*` tables — defined in schema but **no CRUD**

### Commands (Absent)

- `/learn` — does not exist
- `/query` — does not exist
- `/report` — does not exist
- `/nudge` — does not exist

### Distributed System (Not Implemented)

- **Vampire swarm** (8-12 workers) — basic BLPOP loop only
- **Scout offloaders** — no separate node types
- **Queue semantics** — simple list, no priority, no dead-letter, no lease/ack

### Lineage (Unenforced)

- **V2 atoms** have no evidence binding (just simple `knowledge_atoms` table)
- **V3 atom_evidence** table exists in schema but **no writes**
- **Lineage-first** is a stated principle but not operational

---

## Architecture Drift Assessment

| Aspect | Documented (README) | Actual (Code) | Gap |
|--------|---------------------|---------------|-----|
| Storage triad | Postgres + Chroma + Redis | Redis + Chroma only | **Postgres missing** |
| Commands | `/learn`, `/query`, `/report`, `/nudge` | `/research`, `/memory`, `/status` | **Surface mismatch** |
| Pipeline | Modular (frontier/crawler/smelter) | Monolithic (`research_topic`) | **Decomposition absent** |
| Workers | Distributed swarm (8-12) | Basic single worker type | **Distribution minimal** |
| Knowledge | Atoms with lineage (V3) | Simple atoms (V2) | **Lineage not enforced** |
| Mission state | Explicit FSM | Implicit, in-memory | **State machine missing** |

**Verdict:** The system is **architecturally divergent** from its documentation.

---

## Critical Implications for Gauntlet

### If We Continue As-Is

- Phases 02-18 will repeatedly "verify" unimplemented features → all return PARTIAL/FAIL
- Wasted effort auditing dead code and unconnected schemas
- No actionable fixes — just documentation of failure

### Path A — Harden V2

**Accept current system as reality** and:

- Refocus gauntlet on V2 stack (Redis+Chroma)
- Update PHASE 02 to validate V2 boot, not V3
- Drop triad enforcement (it's not real)
- Audit actual commands (`/research`, `/memory`) and retrieval
- Harden what actually works

**Result:** Production-grade V2 system with clear upgrade path to V3 later.

### Path B — Activate V3

**Implement missing V3 before auditing**:

- Phase 01.5 → design V3 activation plan
- New Phase 02 → build Postgres integration, command surface, pipeline split
- Then run gauntlet on newly implemented V3

**Result:** Actually build the system you described, then verify it.

---

## Immediate Required Decision

> **Choose Path A or Path B before Phase 02.**

- **Path A:** Reality check. Harden what exists. Defer V3 to separate effort.
- **Path B:** Build V3 first, then verify. This is implementation, not hardening.

**Hybrid is not possible** — you cannot "harden" a system whose core architecture (triad, commands, pipeline) is not present.

---

## Recommendation

Given:
- You have a **working V2 system** (research produces results)
- V3 is **complex and incomplete**
- Time/energy constraints likely exist

👉 **Path A (Harden V2) is the pragmatic choice.**

BUT if your strategic goal is **knowledge distillation with guaranteed lineage**, you **must** do Path B eventually.

---

**Next step:** Create DECISION.md selecting a path and justifying it.
