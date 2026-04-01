# Sheppard V3 — CLAUDE.md

## Project State

**Current Milestone:** v1.2 — Derived Insight & Report Excellence Layer  
**Previous Milestone:** v1.1 — Performance & Observability (✅ SHIPPED 2026-03-31)

## Active Phase: 12-A — Derived Claim Engine

### Status: 🟡 IN PROGRESS

**What's been built (12-A done):**
- ✅ `src/research/derivation/engine.py` — DerivationEngine, DerivedClaim, compute_delta, compute_percent_change, compute_rank
- ✅ `src/research/derivation/__init__.py` — module exports
- ✅ `src/research/reasoning/assembler.py` — modified: added `derived_claims` to EvidencePacket, calls `DerivationEngine().run(items_parallel)`
- ✅ `tests/research/derivation/test_engine.py` — 18 tests (all passing)
- ✅ All 50 tests pass (18 derivation + 24 ranking + 8 phase-11 invariants, zero regressions)

**What's remaining (12-A todo):**
- ⬜ Extend `src/retrieval/validator.py` to verify derived claims (also 12-B)
- ⬜ Create `12-A-SUMMARY.md` artifact
- ⬜ Commit changes

## Next Phase: 12-B — Dual Validator Extension

### Status: ⬜ PLANNED, NOT STARTED

**Plan:** 12-B-PLAN.md written  
**Purpose:** Extend `validate_response_grounding()` to detect multi-atom numeric relationships, recompute from cited atoms, and verify correctness.

**Tests to write:**
- test_validator_correct_derived_delta (correct % → PASS)
- test_validator_correct_derived_percent (correct % → PASS)
- test_validator_incorrect_derived_delta (wrong number → FAIL)
- test_validator_incorrect_derived_percent (wrong number → FAIL)
- test_validator_single_citation_still_passes (no regression)
- test_validator_non_comparative_multi_citation (skip derived check)
- test_validator_kill_test_incorrect_percentage (validator catch)

## Phase Queue for v1.2

| Phase | Plan | Research | Status | Key Focus |
|-------|------|----------|--------|-----------|
| 12-A | ✅ PLAN.md | ✅ | 🟡 Partial | Derived Claim Engine |
| 12-B | ✅ PLAN.md | — | ⬜ Planned | Dual Validator Extension |
| 12-C | — | ✅ CONTEXT.md | ⬜ Planned | Claim Graph Builder |
| 12-D | — | ✅ CONTEXT.md | ⬜ Planned | Section Planner (evidence-aware) |
| 12-E | — | ✅ CONTEXT.md | ⬜ Planned | Two-stage synthesis + Frontier scope fix |
| 12-F | — | ✅ CONTEXT.md | ⬜ Planned | Adversarial Critic |

## Spec Authority (12-A)

- Derived claims: deterministic, LLM-free, pure functions, SKIP on failure
- 3 rules only: delta, percent_change, rank
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
| src/retrieval/validator.py | ⬜ Pending | 12-A + 12-B extension needed |
| tests/research/derivation/test_engine.py | ✅ Created | 18 tests passing |
| tests/retrieval/test_validator_derived.py | ⬜ Pending | 12-B tests needed |

## Git State

- Tag: v1.0, v1.1 exist
- Tag: v1.2 not yet created
- Latest commit: "chore: archive v1.1 milestone"
- Uncommitted changes: 12-A implementation files

## Working Directory

`/home/bamn/Sheppard`

## Running Tests

```bash
python -m pytest tests/research/derivation/test_engine.py -v          # 12-A tests
python -m pytest tests/research/ -x -q                                # Full research suite
python -m pytest tests/research/reasoning/test_*.py -v                # Phase 11 + ranking
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