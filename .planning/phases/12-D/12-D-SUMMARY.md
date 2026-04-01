# Phase 12-D Summary — Evidence-Aware Section Planner

**Status:** COMPLETE
**Date:** 2026-04-01
**Milestone:** v1.2 — Derived Insight & Report Excellence Layer

## What Was Built

| File | Action | Description |
|------|--------|-------------|
| `src/research/reasoning/section_planner.py` | Created | EvidenceAwareSectionPlanner, EnrichedSectionPlan, SectionMode enum |
| `tests/research/reasoning/test_section_planner.py` | Created | Comprehensive tests for plan generation, mode assignment, budgets |
| `src/research/reasoning/analytical_operators.py` | Extended | Integrated analytical bundle detection into mode logic |
| `src/research/graph/evidence_graph.py` | Consumed | Used for entity clustering and topology |

## Planner Capabilities

- Clusters atoms by entity metadata using `EvidenceGraph.index_by_entity`.
- Assigns `SectionMode` per cluster: DESCRIPTIVE, COMPARATIVE, ADJUDICATIVE, IMPLEMENTATION, SURVEY.
- Computes evidence budgets and target length ranges based on atom counts.
- Identifies contradiction obligations and atom pairs for gate verification.
- Flags allowed derived claims per section (scope enforcement).
- Produces deterministic, LLM-free `EnrichedSectionPlan` list.

## Test Coverage

- `tests/research/reasoning/test_section_planner.py`: 216 lines covering clustering, mode assignment, budget calculation, contradiction handling.
- All tests pass; integration with 12-C graph and 12-B analytical bundles verified.
- Phase 11 invariants preserved.

## Key Design Decisions

- **Deterministic ordering**: Plans sorted by cluster size desc, then entity name; order field is 1-indexed.
- **Contradiction detection**: Propagates from graph contradiction nodes to plan for gate 3.
- **Allowed derived claims**: Section scopes restrict derivations to those whose source atoms are fully contained in the section's cluster.
- **Forbidden extrapolations**: Other entity names listed to warn writer against scope creep.
- **Refusal threshold**: If `budget < _MIN_ATOMS_BEFORE_REFUSAL` (2), `refusal_required=True` (12-E handles with placeholder).

## Next Phases

12-E (Multi-Pass Composition Pipeline) consumes EnrichedSectionPlan to produce section drafts.
