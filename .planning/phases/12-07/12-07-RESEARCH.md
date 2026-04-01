# Phase 12-07: Ranking Improvements (Constraint-Safe) — Research

**Researched:** 2026-03-31
**Domain:** Post-retrieval relevance scoring and atom reordering within existing V3 retrieval pipeline
**Confidence:** HIGH

---

## Summary

Phase 12-07 adds a post-retrieval reordering step to the existing V3 retrieval pipeline. Atoms are already fetched from ChromaDB (up to `max_results` limit); this phase inserts a scoring pass that reorders them before they are packed into `EvidencePacket`. No atoms are dropped, no new queries are issued, and no truth contract invariants are touched.

The scoring infrastructure is already partially in place. `RetrievedItem` in `src/research/reasoning/retriever.py` already has `composite_score` defined with weights for `relevance_score`, `trust_score`, recency, `tech_density`, and `project_proximity`. `V3Retriever` already populates `relevance_score` (from Chroma distance), `trust_score`, `recency_days`, and `tech_density` from atom metadata on every retrieval call. The gap is that `_build_from_context` in `assembler.py` currently sorts only by `global_id` (a deterministic lexical sort) and ignores `composite_score` entirely.

The minimal change is: make `_build_from_context` sort by composite score (descending) as the primary key, retaining `global_id` as a tiebreaker for determinism, when a scoring flag is active on the `RetrievalQuery`. The default must preserve the current behavior so no existing tests break.

**Primary recommendation:** Add an opt-in `enable_ranking: bool = False` field to `RetrievalQuery`. When `True`, `_build_from_context` sorts by `(composite_score DESC, global_id ASC)` instead of `global_id` alone. Scoring weights live in a `RankingConfig` dataclass that ships with sensible defaults. Both single-query (`retrieve`) and batch (`retrieve_many`) paths flow through `_build_from_context`, so one change covers both paths.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RANK-01 | Introduce relevance scoring (cosine similarity + recency + source authority) within retrieval limit | `composite_score` property on `RetrievedItem` already combines these signals; needs activation |
| RANK-02 | Must remain deterministic: same query + same corpus + same seed → identical ordering | `global_id` tiebreaker on equal scores; no RNG introduced; sort is stable |
| RANK-03 | No hard filtering: all retrieved atoms (up to limit) still returned; just reordered | Sort replaces sort; no items removed |
| RANK-04 | Scoring parameters configurable via `RetrievalQuery` options; default preserves current behavior | `enable_ranking=False` default + `RankingConfig` dataclass with overridable weights |
</phase_requirements>

---

## Standard Stack

### Core (no new dependencies)

| Library | Current Use | Role in Phase |
|---------|-------------|---------------|
| Python stdlib `sorted()` | Already used in `_build_from_context` | Stable sort by composite key — no new import |
| Python `dataclasses` | Already used for `RetrievalQuery`, `EvidencePacket` | `RankingConfig` dataclass |
| `pytest` / `pytest-asyncio` | 99+ tests passing | New ranking unit tests |

No new third-party packages are required. All scoring signals are already stored on `RetrievedItem` fields.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-process sort on existing fields | External re-ranking model (cross-encoder) | Cross-encoder: better quality, but adds latency + new dependency, violates constraint-safe scope |
| Inline `sorted()` in `_build_from_context` | Separate `ranker.py` module | Separate module: cleaner, easier to test, preferred |
| `enable_ranking` flag on `RetrievalQuery` | Separate ranked/unranked query types | Flag: simpler API, backwards-compatible, honors RANK-04 |

---

## Architecture Patterns

### Existing Pipeline (where ranking slots in)

```
V3Retriever.retrieve(query)          ← Chroma returns atoms ordered by vector distance
  └─ Returns RoleBasedContext
       └─ ctx.evidence = [RetrievedItem, ...]   ← already has relevance_score, trust_score, etc.

EvidenceAssembler._build_from_context(...)
  └─ collected.sort(key=lambda pair: pair[0]['global_id'])   ← CURRENT: lexical sort only
  └─ packet.atoms = [sorted atoms]                            ← what synthesis sees
```

The ranking step replaces the sort key inside `_build_from_context`. Nothing else moves.

### Recommended Project Structure (additions only)

```
src/research/reasoning/
├── retriever.py          # RetrievalQuery gets enable_ranking + RankingConfig fields
├── ranking.py            # NEW: RankingConfig dataclass + apply_ranking() function
├── assembler.py          # _build_from_context calls apply_ranking() when enabled
└── v3_retriever.py       # No changes needed

tests/research/reasoning/
├── test_phase11_invariants.py    # EXISTING — must pass unchanged
├── test_concurrent_assembly.py   # EXISTING — must pass unchanged
└── test_ranking.py               # NEW: ranking unit tests
```

### Pattern 1: Opt-in via RetrievalQuery field

```python
# src/research/reasoning/retriever.py
@dataclass
class RankingConfig:
    weight_relevance: float = 0.35
    weight_trust: float = 0.20
    weight_recency: float = 0.10
    weight_tech_density: float = 0.15
    weight_project_proximity: float = 0.20
    recency_halflife_days: int = 365

@dataclass
class RetrievalQuery:
    text: str
    # ... existing fields unchanged ...
    enable_ranking: bool = False          # RANK-04: default preserves current behavior
    ranking_config: Optional[RankingConfig] = None  # None → use RankingConfig defaults
```

`composite_score` on `RetrievedItem` already implements this formula. `RankingConfig` allows callers to override weights without forking the method.

### Pattern 2: `apply_ranking()` in ranking.py

```python
# src/research/reasoning/ranking.py
from typing import List, Tuple
from research.reasoning.retriever import RetrievedItem, RankingConfig

def compute_composite_score(item: RetrievedItem, cfg: RankingConfig) -> float:
    recency_factor = max(0.2, 1.0 - (item.recency_days / cfg.recency_halflife_days))
    return (
        item.relevance_score      * cfg.weight_relevance
        + item.trust_score        * cfg.weight_trust
        + recency_factor          * cfg.weight_recency
        + item.tech_density       * cfg.weight_tech_density
        + item.project_proximity  * cfg.weight_project_proximity
    )

def apply_ranking(
    collected: List[Tuple[dict, str]],  # (atom_dict, atom_id) pairs
    items: List[RetrievedItem],
    cfg: RankingConfig
) -> List[Tuple[dict, str]]:
    """
    Sort collected atom pairs by composite score (desc), with global_id as
    deterministic tiebreaker (asc). Returns new sorted list; does not mutate input.
    """
    scored = [
        (pair, compute_composite_score(item, cfg))
        for pair, item in zip(collected, items)
    ]
    scored.sort(key=lambda x: (-x[1], x[0][0]['global_id']))
    return [pair for pair, _ in scored]
```

Note: `collected` in `_build_from_context` contains `(atom_dict, atom_id)` pairs. To sort by item scores we need a parallel reference to the original `RetrievedItem` objects. The easiest approach is to keep items alongside their collected pairs during the dedup loop.

### Pattern 3: Integration in `_build_from_context`

The current dedup loop in `assembler.py`:

```python
# CURRENT (assembler.py _build_from_context)
collected.sort(key=lambda pair: pair[0]['global_id'])
```

Becomes:

```python
# NEW
if query is not None and getattr(query, 'enable_ranking', False):
    from research.reasoning.ranking import apply_ranking
    cfg = query.ranking_config or RankingConfig()
    collected = apply_ranking(collected, items_for_ranking, cfg)
else:
    collected.sort(key=lambda pair: pair[0]['global_id'])
```

The signature of `_build_from_context` must accept the optional `RetrievalQuery` reference, or the ranking config can be passed as a separate parameter. Either is acceptable; passing the query object is cleaner.

### Anti-Patterns to Avoid

- **Removing items:** `apply_ranking` must return exactly `len(collected)` pairs. No filtering.
- **Non-deterministic tiebreaker:** Do NOT use float score alone as the sort key. Two atoms with equal score would produce platform-dependent ordering. Always use `global_id` as tiebreaker.
- **Mutating RetrievedItem:** Do not write `item.citation_key` or any field during ranking. Citation assignment happens in `build_context_block`, not here.
- **Ranking in V3Retriever:** Do not add ranking logic to `retrieve()` or `retrieve_many()`. Those are responsible for fetching from Chroma. Ranking belongs in the assembler's packing step.
- **Shared mutable state across sections:** `apply_ranking` must be a pure function. It must not accumulate cross-section state.
- **Changing `composite_score` property on `RetrievedItem`:** The existing property uses hardcoded weights. The new `RankingConfig` should be passed to `compute_composite_score` in `ranking.py` rather than modifying the property (which would affect any callers relying on the old weights).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stable sort with compound key | Custom merge-sort | Python `sorted()` with tuple key | stdlib sort is stable (Python guarantee); compound key `(-score, global_id)` fully deterministic |
| Score normalization | Custom normalization layer | Existing field ranges (all 0-1 or bounded) | All inputs are already normalized; no extra step needed |
| Cross-encoder re-ranking | Local model invocation | Not in scope | Constraint-safe scope explicitly bans new dependencies |

---

## Common Pitfalls

### Pitfall 1: Breaking the determinism invariant with float comparison
**What goes wrong:** Two atoms may have composite scores that differ by less than float epsilon. If sorted only by score, result is non-deterministic across Python versions or platforms.
**Why it happens:** IEEE 754 float arithmetic is deterministic per-machine but not across platforms.
**How to avoid:** Always use a secondary sort key that is lexically stable. `global_id` (a string) is suitable and already used in the current sort.
**Warning signs:** Flaky test ordering in `test_atom_order_sorted` — the test checks exact `global_id` sequence.

### Pitfall 2: `_build_from_context` signature change breaks existing callers
**What goes wrong:** `_build_from_context` is called from both `build_evidence_packet` (single-query path) and `assemble_all_sections` (batch path). Adding a required parameter breaks one caller if the other is not updated.
**Why it happens:** Internal helper used in two code paths.
**How to avoid:** Make the new ranking parameter optional with a `None` default. When `None`, fall through to the existing `global_id` sort. This is the "default preserves current behavior" guarantee of RANK-04.
**Warning signs:** `TypeError` at call sites in `build_evidence_packet`.

### Pitfall 3: Test `test_atom_order_sorted` asserts exact global_id sequence
**What goes wrong:** `test_phase11_invariants.py::test_atom_order_sorted` asserts `gids == ['[A]', '[B]']`. With ranking enabled, order could change. With ranking disabled (default), it must still pass.
**Why it happens:** The test exercises determinism invariant, not ranking behavior.
**How to avoid:** Ranking is opt-in (`enable_ranking=False` default). The test does not pass a custom query, so the default path (lexical sort) remains active. No changes needed to this test.
**Warning signs:** Failing `test_atom_order_sorted` indicates the default path is broken.

### Pitfall 4: `items_for_ranking` not available in `_build_from_context`
**What goes wrong:** The dedup loop builds `collected: List[(atom_dict, atom_id)]` but discards the original `RetrievedItem`. Ranking needs item fields (`relevance_score`, `trust_score`, etc.) that are on the item, not in `atom_dict`.
**Why it happens:** `_build_from_context` strips rich item metadata when building the minimal `atom_dict` representation.
**How to avoid:** During the dedup loop, accumulate a parallel list `items_parallel: List[RetrievedItem]` alongside `collected`. Pass both to `apply_ranking`. This is a localized change within the loop — no interface changes needed.
**Warning signs:** `AttributeError` when accessing `relevance_score` from `atom_dict`.

### Pitfall 5: Ranking applied inside `retrieve_many` breaks batch-path tests
**What goes wrong:** If ranking is embedded in `V3Retriever.retrieve_many`, the batch tests in `test_concurrent_assembly.py` may fail because they mock `retrieve_many` return values and do not expect reordering.
**Why it happens:** Tests mock the retriever, not the assembler internals.
**How to avoid:** All ranking occurs in `_build_from_context` (assembler layer), not inside the retriever. The retriever remains a pure fetch layer.

---

## Code Examples

### Exact current sort in `_build_from_context` (the line to extend)

```python
# src/research/reasoning/assembler.py, line 151
# Source: direct code read
collected.sort(key=lambda pair: pair[0]['global_id'])
```

### `composite_score` on `RetrievedItem` (already implemented)

```python
# src/research/reasoning/retriever.py, lines 58-70
# Source: direct code read
@property
def composite_score(self) -> float:
    recency_factor = max(0.2, 1.0 - (self.recency_days / 365))
    return (
        self.relevance_score * 0.35
        + self.trust_score * 0.20
        + recency_factor * 0.10
        + self.tech_density * 0.15
        + self.project_proximity * 0.20
    )
```

### Deterministic compound sort key (correct pattern)

```python
# Correct: descending score, ascending global_id as tiebreaker
collected.sort(key=lambda pair: (-score_map[pair[1]], pair[0]['global_id']))
```

---

## Runtime State Inventory

Step 2.5: SKIPPED — this phase is not a rename/refactor/migration. No runtime state inventory required.

---

## Environment Availability

Step 2.6: No new external dependencies. All required tools are already in use.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python `sorted()` stdlib | Ranking sort | Built-in | Always | — |
| `pytest` / `pytest-asyncio` | New ranking tests | Already installed | (in use) | — |

---

## Validation Architecture

`workflow.nyquist_validation` is not set to `false` in `.planning/config.json` — validation section is included.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | No dedicated config detected; tests use `sys.path.insert` convention |
| Quick run command | `cd /home/bamn/Sheppard && python -m pytest tests/research/reasoning/ -x -q` |
| Full suite command | `cd /home/bamn/Sheppard && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RANK-01 | Atoms reordered by composite score when enabled | unit | `pytest tests/research/reasoning/test_ranking.py::test_ranking_reorders_by_score -x` | Wave 0 |
| RANK-02 | Same inputs always produce identical ordering | unit | `pytest tests/research/reasoning/test_ranking.py::test_ranking_is_deterministic -x` | Wave 0 |
| RANK-03 | No atoms dropped — len(output) == len(input) | unit | `pytest tests/research/reasoning/test_ranking.py::test_ranking_preserves_all_atoms -x` | Wave 0 |
| RANK-04 | Default (enable_ranking=False) preserves current global_id sort | unit | `pytest tests/research/reasoning/test_phase11_invariants.py::test_atom_order_sorted -x` | Exists |
| RANK-04 | Custom RankingConfig weights applied | unit | `pytest tests/research/reasoning/test_ranking.py::test_ranking_config_weights -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/research/reasoning/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green (99+ existing tests + new ranking tests) before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/research/reasoning/test_ranking.py` — covers RANK-01, RANK-02, RANK-03, RANK-04 (custom config)
- [ ] `src/research/reasoning/ranking.py` — new module (implementation, not test gap, but must exist before tests run)

*(Existing test infrastructure covers RANK-04 default behavior via `test_atom_order_sorted`.)*

---

## Open Questions

1. **Where does `_build_from_context` receive the query reference?**
   - What we know: `_build_from_context(mission_id, section, context, packet)` does not currently accept a query.
   - What's unclear: Whether to pass the full `RetrievalQuery` or just `(enable_ranking, ranking_config)`.
   - Recommendation: Add `query: Optional[RetrievalQuery] = None` as the last parameter. Both call sites (`build_evidence_packet` and `assemble_all_sections`) have the query in scope and can pass it.

2. **Should `project_proximity` be populated in this phase?**
   - What we know: `project_proximity` is defined on `RetrievedItem` and defaults to `0.0`. `V3Retriever` never sets it.
   - What's unclear: Whether to wire it up or leave it at 0.0 for now.
   - Recommendation: Leave at `0.0` for this phase. The scoring formula still functions; it just assigns zero weight to that signal. A future phase can populate it. Document this as intentional in code comments.

3. **Should `retrieve_many` respect per-query `enable_ranking` flags?**
   - What we know: Batch mode uses `common_limit = max(limits)` and returns contexts per query. Ranking is applied in `_build_from_context`, not in the retriever.
   - What's unclear: Nothing — ranking is assembler-side. The retriever does not need to know about it.
   - Recommendation: No changes to `V3Retriever`. Confirmed safe.

---

## Sources

### Primary (HIGH confidence)

- Direct code read: `src/research/reasoning/v3_retriever.py` — retrieve, retrieve_many, _build_from_context, _days_since
- Direct code read: `src/research/reasoning/retriever.py` — RetrievedItem.composite_score, RetrievalQuery fields, RoleBasedContext
- Direct code read: `src/research/reasoning/assembler.py` — _build_from_context sort logic (line 151), _build_from_context signature
- Direct code read: `tests/research/reasoning/test_phase11_invariants.py` — invariants that must not regress, especially `test_atom_order_sorted`
- Direct code read: `tests/research/reasoning/test_concurrent_assembly.py` — concurrent assembly tests that must not regress
- Direct code read: `.planning/REQUIREMENTS.md` — RANK-01 through RANK-04 definitions

### Secondary (MEDIUM confidence)

- `.planning/phases/12-02.2/12-02.2-SUMMARY.md` — confirms V3Retriever.retrieve_many architecture and test baseline (99 tests passing)
- `.planning/phases/12-03/12-03-CONTEXT.md` — confirms synthesis is downstream; ordering of atoms reaches synthesis prompt

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all signals already present in codebase
- Architecture: HIGH — change is localized to one sort call in `_build_from_context`; integration points fully traced
- Pitfalls: HIGH — identified from code structure; float tiebreaker and signature-change risks are concrete

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable internal codebase; no external library dependency)
