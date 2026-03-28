# Phase 01.5 — V3 Activation Decision

**Date:** 2025-03-27
**Based on:** Phase 01 Ground-Truth System Inventory

---

## Selected Path

**B — Activate V3**

---

## Decision

Sheppard will not be re-scoped downward to V2 as the production identity.
The Phase 01 findings show that the currently running system is a **V2 operational core** with **V3 aspirational documentation and partial/unwired V3 code surfaces**.

Because the intended product identity depends on:

* canonical truth in Postgres
* lineage-bearing knowledge atoms
* interactive querying over accumulated knowledge
* explicit command surfaces such as `/learn` and `/report`
* decomposed asynchronous pipeline behavior rather than a monolithic research call

…the correct path is to **complete the missing V3 foundations first**, then continue the hardening gauntlet against the real V3 implementation.

---

## Why Path A Was Rejected

Path A would harden the current V2 core, but it would lock the system around the wrong architectural identity:

* no real triad memory contract
* no canonical Postgres-backed lineage
* no true V3 command surface
* no implemented frontier/discovery/smelter separation
* no evidence-backed basis for the current V3 README claims

That would produce a more stable V2 while preserving a strategic mismatch between implementation and product intent.

---

## Immediate Consequence

The hardening gauntlet cannot continue unchanged into Phase 02.
Instead, the program must pivot into **V3 activation work** before resuming architecture verification.

---

## New Program Order

1. Freeze the current Phase 02–18 sequence (as designed for post-V3 verification).
2. Insert a new V3 activation phase set.
3. Implement the minimum required V3 foundations.
4. Resume the hardening gauntlet only after those foundations exist in reachable runtime paths.

---

## Minimum V3 Activation Scope

The following are required before the remaining gauntlet has architectural meaning:

### 1. Postgres Canonical Truth Integration

- real schema application (create all V3 tables)
- real writes from pipeline execution (mission, source, atom, evidence)
- mission/source/atom/report lineage stored in Postgres
- Postgres becomes authoritative rather than decorative

### 2. Command Surface Alignment

Implement or alias the intended V3 surfaces:

- `/learn` — trigger research mission
- `/query` — interactive query over accumulated knowledge
- `/report` — generate master brief from atoms
- `/nudge` — steer frontier in real-time

The system must expose the interaction model described by the docs, not a different V2 command vocabulary.

### 3. Pipeline Decomposition

The monolithic `research_topic()` must be split into real operational stages:

- **Frontier** — topic decomposition, concept generation
- **Discovery** — search/URL harvesting
- **Queue** — handoff to workers (Redis)
- **Scraping/Normalization** — fetch and chunk content
- **Smelting** — atom extraction with evidence
- **Storage/Indexing** — write to Postgres + Chroma

These do not need maximal sophistication immediately, but they must be real, separated, and observable (can be async tasks within the same process initially).

### 4. Atom + Lineage Enforcement

- structured atom schema in live use (fact/claim/tradeoff/etc)
- source-to-atom linkage (atom_evidence)
- mission-to-source linkage
- report inputs traceable to stored atoms
- validation rules preventing lineage-free storage (atoms without evidence rejected)

---

## Gate to Resume the Gauntlet

The next verification phase (hardening gauntlet) may proceed only when **all** of the following are **true**:

- [ ] Postgres is in the live write/read loop (not just schema file)
- [ ] `/learn` exists as a real command (can start a mission)
- [ ] Pipeline stages are operationally separable (can observe each stage's output)
- [ ] Atoms and lineage are actually stored and retrievable (query returns evidence-backed atoms)

Until these are met, continuing the gauntlet would produce noise — we'd be auditing absent features.

---

## Program Status

| Aspect | Before (V2) | After (V3 Target) |
|--------|-------------|-------------------|
| Storage | Redis + Chroma | Postgres + Chroma + Redis |
| Commands | `/research`, `/memory` | `/learn`, `/query`, `/report`, `/nudge` |
| Pipeline | Monolithic | Decomposed (frontier→discovery→crawl→smelt→index) |
| Knowledge | Simple atoms | Atoms with lineage (evidence) |
| Identity | V2 core with V3 docs | V3 core matching docs |

**Current state:** V2 operational core
**Target state:** V3 activated foundation
**Decision:** Build the missing V3 core, then resume the gauntlet

---

## Final Rationale

The purpose of this program is not to cosmetically align documentation.
It is to make Sheppard actually become the system it claims to be.

Therefore the correct move is to **activate V3, not institutionalize V2**.

---

**Next artifact:** `PHASE-02-V3-ACTIVATION-PLAN.md` — concrete implementation plan to build the missing V3 foundations.
