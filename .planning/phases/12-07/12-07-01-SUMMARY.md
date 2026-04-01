---
phase: 12-07
plan: "01"
subsystem: research/reasoning
tags: [ranking, retrieval, assembler, post-retrieval, opt-in]
dependency_graph:
  requires: []
  provides:
    - ranking.py module with RankingConfig, compute_composite_score, apply_ranking
    - RetrievalQuery.enable_ranking and ranking_config fields
    - _build_from_context opt-in ranking via apply_ranking
  affects:
    - src/research/reasoning/assembler.py (_build_from_context, assemble_all_sections)
    - src/research/reasoning/retriever.py (RetrievalQuery)
tech_stack:
  added:
    - src/research/reasoning/ranking.py (new module, stdlib only)
  patterns:
    - TDD red-green cycle for ranking module
    - TYPE_CHECKING guard to avoid circular imports
    - Opt-in feature flag (enable_ranking=False default) preserving backward compat
    - Parallel list pattern (items_parallel) for ranking signal access
key_files:
  created:
    - src/research/reasoning/ranking.py
    - tests/research/reasoning/test_ranking.py
  modified:
    - src/research/reasoning/retriever.py
    - src/research/reasoning/assembler.py
decisions:
  - "RankingConfig defaults match RetrievedItem.composite_score weights (0.35/0.20/0.10/0.15/0.20) for zero-delta behavior at first adoption"
  - "ranking.py uses TYPE_CHECKING guard for RetrievedItem import to avoid circular dependency with retriever.py"
  - "apply_ranking is a pure function: does not mutate inputs, returns new list"
  - "enable_ranking=False by default: all existing call sites unaffected unless explicitly opted in"
  - "Local import of apply_ranking inside _build_from_context conditional branch to avoid top-level circular import risk"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-04-01"
  tasks_completed: 3
  files_created: 2
  files_modified: 2
---

# Phase 12 Plan 07-01: Ranking Improvements (Constraint-Safe) Summary

**One-liner:** Opt-in post-retrieval atom ranking via RankingConfig composite score (relevance/trust/recency/tech_density/project_proximity) wired into EvidenceAssembler._build_from_context.

## Objective

Activate post-retrieval atom reordering when opted in, improving synthesis quality without touching the truth contract. Atoms are currently sorted only by global_id (lexical), ignoring the composite signal scores already present on every RetrievedItem. This plan creates the ranking module and wires it into the evidence assembler.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 (TDD) | Create ranking.py — RankingConfig, compute_composite_score, apply_ranking | 1444c62 (GREEN), d53fd2f (RED) | src/research/reasoning/ranking.py, tests/research/reasoning/test_ranking.py |
| 2 | Extend RetrievalQuery with enable_ranking and ranking_config fields | 1139cc0 | src/research/reasoning/retriever.py |
| 3 | Wire apply_ranking into _build_from_context in assembler.py | 8cf430d | src/research/reasoning/assembler.py |

## What Was Built

### ranking.py (new module)

- `RankingConfig` dataclass with configurable weights (default: relevance=0.35, trust=0.20, recency=0.10, tech_density=0.15, project_proximity=0.20; sum=1.0)
- `compute_composite_score(item, cfg)` — pure scoring function, replicates existing `RetrievedItem.composite_score` with caller-supplied config
- `apply_ranking(collected, items_parallel, cfg)` — pure sort: (-composite_score, global_id). No atoms dropped. Deterministic.

### retriever.py changes

- `from research.reasoning.ranking import RankingConfig` added to imports
- `RetrievalQuery` gains two new optional fields: `enable_ranking: bool = False` and `ranking_config: Optional[RankingConfig] = None`
- All existing call sites unaffected (new fields have defaults)

### assembler.py changes

- `_build_from_context` signature gains `query: Optional[RetrievalQuery] = None` parameter
- Dedup loop now builds `items_parallel` in parallel with `collected`
- Opt-in sort branch: when `query.enable_ranking=True`, calls `apply_ranking(collected, items_parallel, cfg)`; else falls back to existing `collected.sort(key=lambda pair: pair[0]['global_id'])`
- `build_evidence_packet` call site passes `q` (already in scope)
- `_assemble_all_sections_impl` batch loop updated to `enumerate(zip(...))` and passes `queries[i]`

## Verification Results

- `python -m pytest tests/research/reasoning/ -q` — 28 passed (13 baseline + 15 new ranking tests)
- `from research.reasoning.ranking import RankingConfig, compute_composite_score, apply_ranking` — OK
- `grep enable_ranking src/research/reasoning/retriever.py` — match at line 95
- `grep apply_ranking src/research/reasoning/assembler.py` — match at lines 155, 157
- Phase 11 invariants test: 8 passed

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All fields and logic fully wired. The `project_proximity` weight in RankingConfig is 0.20 by default, but V3Retriever currently sets that field to 0.0 on all items — zero-value input has zero effect. This is documented in the RankingConfig docstring; a future phase will populate it.

## Self-Check: PASSED

Files exist:
- /home/bamn/Sheppard/src/research/reasoning/ranking.py — FOUND
- /home/bamn/Sheppard/tests/research/reasoning/test_ranking.py — FOUND

Commits exist:
- d53fd2f (RED test) — FOUND
- 1444c62 (GREEN impl) — FOUND
- 1139cc0 (retriever) — FOUND
- 8cf430d (assembler) — FOUND
