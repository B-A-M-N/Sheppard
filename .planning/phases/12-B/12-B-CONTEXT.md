# Phase 12-B — Context: Analytical & Comparative Reasoning Layer

## Position in Stack

**12-B = Analysis Primitives** — structured comparative reasoning.

Moves the system beyond "here are facts" to "here is how facts relate": compare/contrast bundles, tradeoff extraction, consensus vs divergence grouping, source authority weighting.

**Master Invariant:** The writer never invents intelligence; it renders intelligence already mechanically assembled upstream.

---

## What's Already Built (✅ Complete — Partial Alignment)

The current 12-B implementation provides **dual validator extension** for verifying derived claims. This is valuable but represents only ONE HALF of the cognitive synthesis vision.

**What exists:**
- `src/retrieval/validator.py` — extended to verify multi-atom numeric relationships
- `tests/retrieval/test_validator_derived.py` — 9 tests for correct/incorrect derived claims
- DUAL_VALIDATOR_REPORT.md — validator extension spec
- 12-B-SUMMARY.md — execution record

**What's missing from the cognitive synthesis framing:**
The validator extension ensures derived claims are CORRECT when written by the LLM. But it doesn't give the SYSTEM new analytical abilities. The system can now VERIFY "A exceeds B by 25%" but cannot yet ASSEMBLE comparative bundles, tradeoff analyses, or consensus/divergence groups for the writer.

---

## What 12-B Must Add (Cognitive Synthesis Layer)

The validator extension is the **safety gate**. Now we need the **intelligence layer** that produces comparative structure upstream.

### Required Analytical Operators

| Operator | Input | Output | Use Case |
|----------|-------|--------|----------|
| **compare_contrast_bundle** | 2+ atoms about same entity/metric | List of agreements, differences, gaps | Competitive analysis, technology comparisons |
| **tradeoff_extraction** | 2+ atoms with pros/cons, strengths/weaknesses | Structured tradeoff matrix | Architecture decisions, framework comparisons |
| **method_result_pairing** | Atoms tagged methodology + results | Paired (method, result) tuples | Science/engineering reports |
| **consensus_divergence** | 3+ atoms with conflicting claims | Cluster of agreed vs disputed | Literature surveys, policy analysis |
| **source_authority_weight** | Atom + source metadata | Authority score per source | Evidence quality grading |
| **change_detection** | 2+ atoms with timestamps, same metric | "X changed from A to B over T" | Historical analysis, evolution tracking |

### How These Operators Work

All are **deterministic**, **LLM-free** functions operating on structured atom data:

```python
def compare_contrast_bundle(atoms: List[RetrievedItem]) -> AnalyticalBundle:
    """Group atoms about same entity, identify what each adds/repeats/conflicts."""
    # 1. Group by topic/entity from metadata
    # 2. Find shared content (lexical overlap threshold)
    # 3. Classify overlap: agreement (same claim, different source), reinforcement (same claim, same source, different phrasing),
    #    contradiction (conflicting claim), elaboration (new detail about same entity)
    # 4. Return structured bundle
```

### Integration with Existing 12-A Engine

Analytical operators consume output from 12-A:
- `compare_contrast_bundle` uses 12-A's ranking and derived deltas
- `consensus_divergence` uses 12-A's conflict rollups
- All operators produce new node types for the claim graph (12-C)

### Files That Will Change

| File | Change |
|------|--------|
| `src/research/reasoning/analytical_operators.py` | NEW — analytical operator implementations |
| `src/research/reasoning/assembler.py` | Call analytical operators after derivation |
| `EvidencePacket` | Add `analytical_bundles` field |
| `tests/research/reasoning/test_analytical_operators.py` | NEW — operator tests |
| `.planning/phases/12-B/ANALYTICAL_OPERATORS.md` | NEW — spec doc |
| `.planning/phases/12-B/COMPARISON_AND_TRADEOFF_SPEC.md` | NEW — comparison spec |

---

## Phase 12-B Success Criteria

- Analytical operators produce structured output from raw atoms
- Compare/contrast bundle groups atoms by entity with agreement/conflict classification
- Tradeoff extraction produces structured tradeoff matrix
- Consensus/divergence identifies clusters of agreeing and conflicting atoms
- Zero LLM calls in analytical operators (all deterministic)
- All 12-B integration tests pass
- Existing 12-A tests still pass (no regression from validator/analytical changes)
