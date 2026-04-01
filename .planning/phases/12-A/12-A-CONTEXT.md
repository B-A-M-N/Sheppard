# Phase 12-A — Context: Derived Claim Engine

## Purpose

Research and context analysis for implementing the Derived Claim Engine — deterministic, LLM-free transformations that produce "insight" claims from retrieved atoms while preserving full provenance and truth guarantees.

---

## Spec Authority

This phase implements the locked spec from the user's authoritative resolution (all ambiguities resolved). That spec specifies:

- **Scope:** delta, percent_change, rank rules only (defers trend/consensus/contradiction_summary)
- **Storage:** Ephemeral on EvidencePacket; not persisted to Postgres
- **Integration:** Inside EvidenceAssembler._build_from_context() after ranking
- **Citation:** Derived claims NOT separately cited; writer cites source atoms only
- **Validator:** Extended to verify arithmetic correctness of derived relationships
- **Determinism:** Sort atoms by global_id; pure functions; no randomness
- **Error handling:** SKIP on failure (never halt pipeline)
- **Performance:** <1ms per claim, O(n log n) max
- **Testing:** Unit + kill tests (order independence, mutation sensitivity, removal failure, validator catch)

---

## Internal Research: Codebase Analysis

### 1. EvidenceAssembler Architecture

**Location:** `src/research/reasoning/assembler.py` (285 lines)

**Current Flow:**
```python
EvidenceAssembler._build_from_context():
  1. Deduplicate atoms from RoleBasedContext
  2. Apply ranking (12-07) if enable_ranking=True
  3. Build packet.atoms + packet.atom_ids_used
  4. Add contradictions from PG if section targets them
```

**Exact Integration Point:**
Line 160: After `collected.sort(key=lambda pair: pair[0]['global_id'])` OR after `apply_ranking(collected, items_parallel, cfg)`
Line 161-165: Unpack into packet

**INSERT DERIVATION BETWEEN:**
After line 160 (ranking/default sort)
Before line 163 (packet unpacking)

**Code to call:**
```python
# After ranking, before packing:
derived = derivation_engine.run(items_parallel)
packet.derived_claims = derived
```

**EvidencePacket Dataclass** (lines 35-42):
```python
@dataclass
class EvidencePacket:
    topic_name: str
    section_title: str
    section_objective: str
    atoms: List[Dict] = field(default_factory=list)
    contradictions: List[Dict] = field(default_factory=list)
    atom_ids_used: List[str] = field(default_factory=list)
    retrieval_profile: Optional[Dict[str, float]] = None
```

**Required modification:** Add `derived_claims: List[DerivedClaim] = field(default_factory=list)`

### 2. Ranking Module Architecture

**Location:** `src/research/reasoning/ranking.py` (107 lines)

**Pattern to follow:** Clean module with RankingConfig dataclass + pure functions
- compute_composite_score() = pure function
- apply_ranking() = pure function; returns new sorted list

**DerivedClaim Engine should follow same pattern:**
- `DerivationConfig` dataclass (optional, for tolerance/epsilon settings)
- `compute_delta()` = pure function over 2 atoms
- `compute_percent_change()` = pure function over 2 atoms
- `compute_rank()` = pure function over N atoms
- `DerivationEngine.run()` = orchestrator

### 3. RetrievedItem Data Structure

**Location:** `src/research/reasoning/retriever.py` (lines 41-72)

```python
@dataclass
class RetrievedItem:
    content: str
    source: str
    strategy: str
    knowledge_level: str = "B"
    item_type: str = "claim"
    relevance_score: float = 0.0
    trust_score: float = 0.5
    recency_days: int = 9999
    tech_density: float = 0.5
    project_proximity: float = 0.0
    is_contradiction: bool = False
    citation_key: Optional[str] = None
    concept_name: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    @property
    def composite_score(self) -> float: ...
```

**Relevant fields for derivation:**
- `content` = source text (need to extract numeric values)
- `metadata` = may contain structured data from atom extraction
- `citation_key` = identifies atom for provenance

### 4. Current Validator Architecture

**Location:** `src/retrieval/validator.py` (171 lines)

**Existing behavior:** `validate_response_grounding(response_text, retrieved_items)`
- Extracts citations [A###] from text
- Splits into segments: text before citation
- For each segment without citation: error "Uncited claim"
- For each cited segment:
  - Lexical overlap ≥2 content words
  - Numeric consistency: claim numbers must appear in atom
  - Entity consistency: capitalized entities must appear in atom

**Extension needed:**
After numeric consistency check, also verify derived relationships (if sentence expresses comparison/delta/percent/rank, recompute from cited atoms and verify).

### 5. Test Infrastructure

**Location:** `tests/research/reasoning/`

**Example from test_ranking.py** (24 tests):
```python
# Path setup at top (existing convention):
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_src = os.path.join(_project_root, "src")
for _p in [_src, _project_root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
```

**Helper function pattern** (from test_phase11_invariants.py):
```python
def make_retrieved_item(atom_id, text, citation_key=None):
    meta = {'atom_id': atom_id, 'citation_key': citation_key}
    return RetrievedItem(
        content=text, source='test_source', strategy='semantic',
        knowledge_level='B', item_type='claim',
        relevance_score=0.9, citation_key=citation_key, metadata=meta
    )
```

### 6. Dependencies Analysis

**What 12-A CAN import:**
- `src/research/reasoning/ranking.py` (for reuse of composite_score if rank rule needs it)
- `src/research/reasoning/retriever.py` (for RetrievedItem, RankingConfig)
- `src/retrieval/validator.py` (to extend validate_response_grounding)

**What 12-A CANNOT import:**
- No LLM client (no generation)
- No external APIs
- No synth_adapter

---

## External Research: Derivation Engine Patterns

### Numeric Extraction from Text

**Problem:** Atoms are natural language strings. Need to reliably extract:
- Numeric values (revenue, dates, percentages, scores)
- Entity names (Company A, Product B, etc.)

**Approaches evaluated:**

1. **Regex-based extraction** (CURRENT validator uses this)
   - `extract_numbers()`: matches integers, decimals with commas
   - `extract_entities()`: capitalized word heuristic
   - ✅ Simple, no deps, already working
   - ❌ Fragile for complex numbers (currency symbols, ranges)

2. **NLP-based extraction** (spaCy, NLTK)
   - ✅ Better entity/number recognition
   - ❌ Extra dependency, slower, overkill for derivation

3. **Structured atom metadata** (atom extraction already captures numbers?)
   - Check if atom metadata contains pre-extracted numeric fields
   - ✅ Fast if available
   - ❌ May not be reliable across all atom sources

**Decision for 12-A:** Use regex-based extraction (matches validator pattern). Add simple numeric parsing from atom content text. Future phases can use structured metadata when available.

### Derivation Rule Patterns in Academic/Engineering

**Delta computation:** Standard subtraction. Edge cases: different units, different time windows.
**Percent change:** `((new - old) / old) * 100`. Edge cases: zero denominator, negative values.
**Ranking:** Sort by numeric metric descending. Edge cases: ties, equal values (use global_id tiebreaker).

### Validator Extension Patterns for Derived Claims

**Academic approach** (used in computational claim verification):
1. Identify numeric claims in text (numbers + comparative language)
2. Extract source atom IDs from citations
3. Recompute expected value from source atoms
4. Compare claimed vs computed: `abs(claimed - computed) <= epsilon`
5. FAIL if difference exceeds tolerance

**Tolerance choice:** `1e-9` for floating point, exact match for integers

### Deterministic Hash for DerivedClaim ID

**Standard approach:** SHA-256 of canonical input
```python
import hashlib
def make_claim_id(rule: str, atom_ids: List[str], config_version: str = "12-A-v1") -> str:
    sorted_ids = sorted(atom_ids)
    raw = f"{rule}:{','.join(sorted_ids)}:{config_version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

---

## Architecture Decisions from Context Review

### Where in the Pipeline?

```
EvidenceAssembler._build_from_context()
  → Retrieve atoms [existing]
  → Deduplicate [existing]
  → Apply ranking [existing]
  → Run DerivationEngine [NEW: line ~161]
  → Unpack into packet [existing]
  → Add contradictions [existing]
```

### What DerivedClaim Data Looks Like?

```python
@dataclass(frozen=True)
class DerivedClaim:
    id: str  # deterministic hash
    rule: str  # "delta" | "percent_change" | "rank"
    source_atom_ids: List[str]  # sorted, canonical
    output: Any  # numeric (delta/rank) or structured (list)
    metadata: Dict[str, Any]  # rule-specific
```

### EvidencePacket Modification?

```python
@dataclass
class EvidencePacket:
    # ... existing fields ...
    derived_claims: List[DerivedClaim] = field(default_factory=list)
```

---

## Existing Tests to Not Break

- `tests/research/reasoning/test_ranking.py` (24 tests)
- `tests/research/reasoning/test_phase11_invariants.py` (8 tests)
- `tests/research/` full suite (39 tests)
- All must continue passing after integration

---

## Constraints Enforced by User Spec

1. **NO persistence** — Derived claims ephemeral, computed on-demand
2. **NO LLM calls** — Pure functions only
3. **NO new citation types** — Writer cites atoms, derivations resolve to atom IDs
4. **SKIP on failure** — Never halt pipeline, never fabricate output
5. **Deterministic** — Sort atoms by global_id, pure functions
6. **<1ms per claim** — O(n log n) max complexity
7. **Three rules only** — delta, percent_change, rank (no trend/consensus/contradiction_summary)
8. **Validator extension** — Must verify derived arithmetic/logic, catch failures

---

## Files That Will Change in 12-A

| File | Change |
|------|--------|
| `src/research/derivation/__init__.py` | NEW — module init |
| `src/research/derivation/engine.py` | NEW — DerivationEngine + rules |
| `src/research/derivation/models.py` | NEW — DerivedClaim dataclass |
| `src/research/reasoning/assembler.py` | MODIFY — add derived_claims to EvidencePacket, call DerivationEngine |
| `src/retrieval/validator.py` | MODIFY — extend validate_response_grounding for derived claims |
| `tests/research/derivation/test_engine.py` | NEW — full test suite (unit + kill tests) |
| `.planning/phases/12-A/DERIVED_CLAIM_SCHEMA.md` | NEW — spec doc |
| `.planning/phases/12-A/DERIVATION_RULES.md` | NEW — rule documentation |
| `.planning/phases/12-A/DERIVATION_VALIDATION.md` | NEW — validator extension doc |

---

## Ready for Planning

All internal and external research complete. Ready for `gsd-planner` or direct PLAN.md generation.
