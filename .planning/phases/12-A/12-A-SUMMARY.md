# Phase 12-A Summary — Derived Claim Engine (Full)

**Status:** COMPLETE
**Date:** 2026-04-01

## What Was Built

| File | Action | Description |
|------|--------|-------------|
| `src/research/derivation/engine.py` | Created + Extended | DerivationEngine, DerivedClaim, all 7 pure rules |
| `src/research/derivation/__init__.py` | Created + Extended | Module exports for all 7 rule functions |
| `src/research/reasoning/assembler.py` | Modified | Added `derived_claims` to EvidencePacket, calls DerivationEngine.run() |
| `tests/research/derivation/test_engine.py` | Created | 18 tests for original 3 rules (delta, percent_change, rank) |
| `tests/research/derivation/test_engine_expansion.py` | Created | 14 tests for 4 new rules (ratio, chronology, rollups) |
| `tests/retrieval/test_validator_derived.py` | Created (12-B) | 9 dual-validator tests |

## Rules Implemented (Total: 7)

| Rule | Function | Output Type | Skip Condition |
|------|----------|-------------|----------------|
| delta | `compute_delta` | `float` (A - B) | Either atom lacks numeric value |
| percent_change | `compute_percent_change` | `float` (%) | Either lacks numeric, or old value is zero |
| rank | `compute_rank` | `List[Tuple[str, float]]` | No atoms have numeric values |
| ratio | `compute_ratio` | `float` (A / B) | Either lacks numeric, or denominator is zero |
| chronology | `compute_chronology` | `dict` (earliest_id, latest_id, delta_seconds) | Fewer than 2 atoms have parseable timestamps |
| simple_support_rollup | `compute_support_rollup` | `dict` (entity: count) | No group meets count >= 2 threshold |
| simple_conflict_rollup | `compute_conflict_rollup` | `dict` (concept: count) | Zero atoms have `is_contradiction=True` |

## Test Coverage

- `tests/research/derivation/test_engine.py`: 18 tests (original 3 rules, all passing)
- `tests/research/derivation/test_engine_expansion.py`: 14 tests (4 new rules, all passing)
- `tests/retrieval/test_validator_derived.py`: 9 tests (dual validator, all passing)
- **Total: 41 tests, 0 failures**

## Key Design Decisions

- **Skip-on-failure**: Every rule returns `None` rather than raising; DerivationEngine wraps each in try/except so one bad rule never halts the pipeline.
- **Deterministic IDs**: `make_claim_id` uses `sha256(rule:sorted_atom_ids:version)[:16]` — same inputs always produce the same 16-char hex ID regardless of call order.
- **No LLM calls**: All 7 rules are pure Python math / metadata inspection. Zero network calls, zero probabilistic outputs.
- **dateutil import is local**: `from dateutil import parser` lives inside `compute_chronology()` body, not at module level — callers that never use chronology pay zero import cost.
- **Ephemeral claims**: DerivedClaim objects live only on EvidencePacket; they are never persisted to Postgres. No new citation types introduced — writers cite source atoms only.
- **CONFIG_VERSION = "12-A-v1"**: Unchanged across the expansion so all claim IDs remain stable.

## Export Interface

All symbols exported from `src/research/derivation/__init__.py`:

```python
DerivedClaim, DerivationConfig, DerivationEngine,
compute_delta, compute_percent_change, compute_rank,
compute_ratio, compute_chronology,
compute_support_rollup, compute_conflict_rollup
```

## Next Phase

12-B is complete (dual validator — `tests/retrieval/test_validator_derived.py`). 12-C (Claim Graph Builder) is next.
