# Sheppard V3 — CLAUDE.md

## Project State

**Current Milestone:** v1.2 — Derived Insight & Report Excellence Layer  
**Previous Milestone:** v1.1 — Performance & Observability (✅ SHIPPED 2026-03-31)
**Post-release focus:** DB-backed authority/application stabilization for the live V3 path

## Active Phase: 12-A — Derived Claim Engine

### Status: ✅ COMPLETE

**What's been built (12-A done):**
- ✅ `src/research/derivation/engine.py` — DerivationEngine, DerivedClaim, compute_delta, compute_percent_change, compute_rank, plus ratio and chronology rules
- ✅ `src/research/derivation/__init__.py` — module exports
- ✅ `src/research/reasoning/assembler.py` — modified: added `derived_claims` to EvidencePacket, calls `DerivationEngine().run(items_parallel)`
- ✅ `tests/research/derivation/test_engine.py` — 18 tests (all passing)
- ✅ `tests/retrieval/test_validator_derived.py` — 7 tests for derived claim validation (all passing)
- ✅ 398 tests collected in the current suite

## Analysis & Rationale: Validation and Core Engine Complete

The derived claim engine and dual-validator extension are fully implemented:

1. **Derivation Engine** (`src/research/derivation/engine.py`): Supports 7 rules — `delta`, `percent_change`, `rank`, `ratio`, `chronology`, `simple_support_rollup`, `simple_conflict_rollup`. All are deterministic, pure functions with no LLM calls. Engine properly splits compute into independent rule methods for testability and graceful failure handling.

2. **Validator** (`src/retrieval/validator.py`): Both single-citation checks and multi-citation derived claim verification are complete. `_verify_derived_claim()` handles `delta` and `percent_change` recomputation; `_validate_multi_citation_block()` handles multi-atom numeric relationships with comparative language detection; entity and lexical overlap checks apply universally.

3. **Tests**: `tests/research/derivation/test_engine.py` covers all 7 rules; `tests/retrieval/test_validator_derived.py` covers correct/incorrect delta, correct/incorrect percent, single-citation regression, non-comparative multi-citation, and kill tests.

## Next Phase: 12-B — Dual Validator Extension

### Status: ✅ COMPLETE

**Plan:** 12-B-PLAN.md written  
**Purpose:** Extend `validate_response_grounding()` to detect multi-atom numeric relationships, recompute from cited atoms, and verify correctness — **IMPLEMENTED**.

The validator already performs full dual-atom validation against derived claims including:
- delta detection/recomputation
- percent_change detection/recomputation  
- lexical overlap (>=2 content words)
- entity consistency
- number presence in cited atoms
- comparative language handling

## Phase Queue for v1.2

| Phase | Plan | Research | Status | Key Focus |
|-------|------|----------|--------|-----------|
| 12-A | ✅ PLAN.md | ✅ | ✅ COMPLETE | Derived Claim Engine |
| 12-B | ✅ PLAN.md | — | ✅ COMPLETE | Dual Validator Extension |
| 12-C | — | ✅ CONTEXT.md | ⬜ Planned | Claim Graph Builder |
| 12-D | — | ✅ CONTEXT.md | ⬜ Planned | Section Planner (evidence-aware) |
| 12-E | — | ✅ CONTEXT.md | ⬜ Planned | Two-stage synthesis + Frontier scope fix |
| 12-F | — | ✅ CONTEXT.md | ⬜ Planned | Adversarial Critic |

## Shipped in v1.2
- **Derived Claim Engine**: Deterministic, non-LLM transformations (delta, percent_change, rank, ratio, chronology, support/conflict rollups) integrated into `EvidencePacket`.
- **Dual Validator**: Extended `validate_response_grounding` in `src/retrieval/validator.py` to verify multi-citation numeric and comparative claims via recomputation.
- **V3 Authority Core**: Initial implementation of `AuthorityStore` and `DomainAuthorityRecord` for technical authority tracking.
- **DB-backed Integration**: Restored live PostgreSQL path for V3 missions with automatic service startup and nullable application evidence bindings.

## Post-v1.2 Stabilization
- **Live DB-backed integration path restored**: `SystemManager.initialize()` now auto-starts local PostgreSQL when the configured V3 DSN targets localhost and the service is down.
- **Application evidence contract fixed**: `application.application_evidence` now supports nullable `authority_record_id`, `atom_id`, and `bundle_id` with a non-empty binding check via `migrations/phase_20_application_evidence_nullable.sql`.
- **Authority feedback persistence fixed**: `AnalysisService` now preserves required authority record identity fields when writing feedback-layer updates.
- **DB-backed E2E coverage added**: live-path integration tests now cover authority synthesis binding, application feedback persistence, and retrieval of authority plus contradictions through the real adapter path.

## Spec Authority (12-A)

- Derived claims: deterministic, LLM-free, pure functions, SKIP on failure
- 7 rules: delta, percent_change, rank, ratio, chronology, simple_support_rollup, simple_conflict_rollup
- Ephemeral on EvidencePacket (not persisted to Postgres)
- No new citation types — writer cites atoms only
- SHA-256 claim ID from sorted atom IDs for determinism
- Tolerance: 1e-9 for floating point verification

## Key Files Modified by v1.2

| File | Modified? | Notes |
|------|-----------|-------|
| src/research/derivation/engine.py | ✅ Created |
| src/research/derivation/__init__.py | ✅ Created |
| src/research/reasoning/assembler.py | ✅ Modified | 12-A integration done |
| src/retrieval/validator.py | ✅ Modified | 12-A + 12-B extension complete |
| tests/research/derivation/test_engine.py | ✅ Created | 18 tests passing |
| tests/retrieval/test_validator_derived.py | ✅ Created | 7 tests passing |

## Git State

- Tag: v1.0, v1.1 exist
- Tag: v1.2 exists and points to `68db57b` (`chore: archive v1.2 milestone`)
- Current HEAD: working tree ahead of `v1.2` with post-release stabilization changes
- Uncommitted changes: DB-backed integration and startup hardening work

## Working Directory

`/home/bamn/Sheppard`

## Running Tests

```bash
python -m pytest tests/research/derivation/test_engine.py -v          # 12-A tests
python -m pytest tests/research/ -x -q                                # Full research suite
python -m pytest tests/research/reasoning/test_*.py -v                # Phase 11 + ranking
pytest -q tests/integration/test_knowledge_pipeline.py \
  tests/integration/test_authority_pipeline_e2e.py \
  tests/integration/test_analysis_application_e2e.py \
  tests/integration/test_retrieval_authority_contradiction_e2e.py \
  tests/integration/test_authority_maturity_flow_e2e.py \
  tests/integration/test_analysis_feedback_loop_e2e.py                # Live DB-backed V3 path
```

# Key Rules
- TDD: write tests first, then implement
- Never weaken truth contract invariants
- All existing tests must pass after each phase
- No LLM calls in derivation engine
- Deterministic: sort atoms by global_id, pure functions
- Skip on failure (never halt pipeline)
- Derived claims ephemeral, not persisted
- No new citation types — writer cites source atoms only
