# Phase 12-A: Derived Claim Engine - Research (V2)

**Researched:** 2026-03-31
**Domain:** Deterministic Relational Intelligence / Computational Synthesis
**Confidence:** HIGH

## Summary

The `DerivationEngine` is the "math heart" of the Sheppard synthesis stack. Its goal is to convert a list of retrieved atoms into high-order relational facts (e.g., "A is 20% larger than B") without using an LLM. This ensures that the intelligence generated is deterministic, verifiable, and free from hallucinations.

This research focuses on expanding the existing engine (which supports `delta`, `percent_change`, and `rank`) with four new critical rules: `ratio`, `chronology`, `simple_support_rollup`, and `simple_conflict_rollup`.

**Primary recommendation:** Refactor the `DerivationEngine` into a **Rule Strategy Pattern** where each computation is a standalone class. This allows the engine to scale to dozens of rules without becoming a "god object" and ensures consistent error handling (SKIP-on-failure) across all derivations.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Pure function contract enforced**: No LLM calls, no side effects.
- **Deterministic IDs via SHA-256**: `sha256(rule:sorted_atom_ids:version)[:16]`.
- **SKIP-on-failure**: Errors never halt the pipeline; failed derivations are simply omitted.
- **EvidencePacket attachment**: Derived claims are attached to the ephemeral `EvidencePacket` during assembly.

### the agent's Discretion
- **Rule implementation logic**: Specific math and extraction logic for `ratio`, `chronology`, and `rollups`.
- **Architecture**: Internal organization of the `DerivationEngine` (recommended: Strategy pattern).
- **Metadata extraction priority**: How to handle cases where numeric/date values are missing from explicit metadata but present in text.

### Deferred Ideas (OUT OF SCOPE)
- **Persisted Derivations**: For now, derived claims are NOT stored in the database (Phase 12-C might change this).
- **Complex Graphs**: Full graph-based reasoning is deferred to Phase 12-C.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DERIV-EXP-01 | Implement `ratio` rule | Formula: `A / B`. Requires zero-division guard. Deterministic pair selection. |
| DERIV-EXP-02 | Implement `chronology` rule | Uses `python-dateutil` for parsing. Computes `(earliest, latest, delta_seconds)`. |
| DERIV-EXP-03 | Implement `support_rollup` | Grouping atoms by `entity_id` or `concept_name` in metadata. |
| DERIV-EXP-04 | Implement `conflict_rollup` | Counting atoms where `is_contradiction=True`. |
| DERIV-EXP-05 | Rule Registry Refactor | Transition from hardcoded methods to a modular rule-based architecture. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `python-dateutil` | 2.9.0 | Date Parsing | Handles fuzzy date formats better than standard `datetime`. |
| `hashlib` | Stdlib | ID Generation | Industry standard for deterministic hashing. |
| `re` | Stdlib | Text Extraction | Necessary for fallback numeric/date extraction from raw content. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `collections` | Stdlib | Rollups | `defaultdict` is the efficient choice for grouping atoms. |
| `math` | Stdlib | Stability | Use `math.isclose` for floating point comparisons in validation. |

**Installation:**
```bash
# Ensure dateutil is present (usually pre-installed with botocore/others)
pip install python-dateutil
```

**Version verification:**
Verified `python-dateutil` 2.9.0.post0 is available in the current environment.

## Architecture Patterns

### Recommended Project Structure
The `DerivationEngine` should move towards a registry-based system:
```
src/research/derivation/
├── __init__.py
├── engine.py           # Orchestrator & Registry
├── base.py             # Abstract Base Class for Rules
└── rules/              # Individual rule implementations
    ├── numeric.py      # delta, percent_change, ratio
    ├── ranking.py      # rank
    ├── temporal.py     # chronology
    └── rollups.py      # support/conflict counts
```

### Pattern 1: Rule Strategy Pattern
**What:** Define an abstract `DerivationRule` class with a `run(items, config)` method.
**When to use:** When the number of transformation rules grows beyond 3-5.
**Example:**
```python
class RatioRule(DerivationRule):
    def run(self, items: List[RetrievedItem]) -> List[DerivedClaim]:
        # Implementation...
        pass
```

### Pattern 2: Deterministic Pairwise Processing
**What:** Sort all items by `citation_key` (or `atom_id`) first, then iterate using `for i in range(len(items)): for j in range(i + 1, len(items)):`.
**Why:** Ensures that for binary rules (like `delta` or `ratio`), `(A, B)` is always processed in the same order regardless of how the retriever returned them.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Date Parsing | Custom Regex | `dateutil.parser.parse` | Handles 100+ edge cases (US vs EU, ISO, relative). |
| Deterministic IDs | Random UUIDs | `hashlib.sha256` | IDs must be identical across runs for the same data. |
| Grouping | Nested Loops | `collections.defaultdict` | cleaner O(N) grouping for rollups. |
| Numeric Extraction | Simple `float()` | Existing `_extract_numbers` regex | Handles commas, currency symbols, and multiple numbers. |

## Common Pitfalls

### Pitfall 1: Ratio Division by Zero
**What goes wrong:** Attempting to compute `A / B` where `B = 0`.
**Why it happens:** Real-world data often contains 0 values for metrics (e.g., "0 downtime").
**How to avoid:** Explicit check `if val_b == 0: return None`.

### Pitfall 2: Chronology "Time Travel"
**What goes wrong:** `recency_days` says Atom A is newer, but `publish_date` in metadata says Atom B is newer.
**Why it happens:** Ingestion time != Publication time.
**How to avoid:** Prioritize `publish_date` (absolute) over `recency_days` (relative). Fall back to `recency_days` ONLY if absolute dates are missing for ALL items.

### Pitfall 3: Rollup Double Counting
**What goes wrong:** Counting the same atom twice in a rollup.
**How to avoid:** Deduplicate input `RetrievedItem` list by `atom_id` before running any rollup rule.

## Code Examples

### 1. Chronology Extraction
```python
from dateutil import parser
from datetime import timezone

def extract_date(item: RetrievedItem):
    # 1. Check metadata
    dt_str = item.metadata.get('publish_date') or item.metadata.get('timestamp')
    if dt_str:
        try:
            return parser.parse(dt_str).astimezone(timezone.utc)
        except:
            pass
    
    # 2. Fallback to recency_days (convert to approximate date)
    # Note: This is less precise but maintains relative order.
    return item.recency_days 
```

### 2. Simple Support Rollup
```python
from collections import defaultdict

def compute_support_rollup(items: List[RetrievedItem]):
    counts = defaultdict(list)
    for item in items:
        # Group by entity or concept
        entity_id = item.metadata.get('entity_id') or item.concept_name
        if entity_id:
            counts[entity_id].append(item.citation_key)
    
    return [
        {"entity": k, "count": len(v), "sources": v} 
        for k, v in counts.items() if len(v) > 1
    ]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LLM-based comparison | Deterministic Derivation | Phase 12-A | Eliminates "hallucinated math". |
| Hardcoded Engine | Rule Registry | Phase 12-A (V2) | Extensibility and testability. |
| Timestamp-only | Multi-source Chronology | Phase 12-A (V2) | Better handling of varied source metadata. |

## Open Questions

1. **Rollup Granularity**: Should we roll up by `entity_id` (precise) or `concept_name` (broader)?
   - **Recommendation**: Try `entity_id` first, fallback to `concept_name`.
2. **Conflict Definition**: Does `is_contradiction=True` alone define a conflict group?
   - **Recommendation**: Yes, items flagged as contradictions within the same `EvidencePacket` are assumed to be part of the same local conflict rollup.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` |
| Config file | `pytest.ini` |
| Quick run command | `pytest tests/research/derivation/test_engine.py` |
| Full suite command | `pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DERIV-EXP-01 | Compute ratio A/B | Unit | `pytest tests/research/derivation/test_engine.py -k ratio` | ❌ Wave 0 |
| DERIV-EXP-02 | Chronological ordering | Unit | `pytest tests/research/derivation/test_engine.py -k chronology` | ❌ Wave 0 |
| DERIV-EXP-03 | Support rollup counts | Unit | `pytest tests/research/derivation/test_engine.py -k support` | ❌ Wave 0 |
| DERIV-EXP-04 | Conflict rollup counts | Unit | `pytest tests/research/derivation/test_engine.py -k conflict` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/research/derivation/test_engine_expansion.py` — New test file for expanded rules.
- [ ] `src/research/derivation/rules/` — New directory for modular rules.

## Sources

### Primary (HIGH confidence)
- `src/research/derivation/engine.py` — Existing implementation reviewed.
- `src/research/reasoning/retriever.py` — `RetrievedItem` structure verified.
- `python-dateutil` Documentation — Verified for fuzzy date handling.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Libraries are stable and available.
- Architecture: HIGH - Strategy pattern is industry standard for this use case.
- Pitfalls: MEDIUM - Real-world date formats are notoriously messy.

**Research date:** 2026-03-31
**Valid until:** 2026-04-30
