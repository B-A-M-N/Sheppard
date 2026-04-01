# Phase 12-A Research: Derived Claim Engine

## Research Scope

Investigate implementation patterns for a deterministic, LLM-free derivation engine that computes derived facts (delta, percent_change, rank) from retrieved knowledge atoms while preserving full provenance and truth guarantees.

---

## External Research Findings

### 1. Deterministic Derivation Pattern (Academic/Production)

**What exists in production systems:**
- **IBM Watson**: Uses "claim graphs" with derived relationships; derivations always trace to source facts via provenance IDs
- **DeepMind AlphaGeometry**: Separates "knowledge layer" from "derivation layer"; derivation uses formal rules only (no LLM in derivation)
- **Wolfram Alpha**: Derivations are deterministic transforms; each fact has citation to source data

**Key pattern**: "Interpretation = deterministic transform over structured evidence" — not speculation, but formal computation.

**Relevant for 12-A**: Delta, percent_change, and rank are all arithmetic operations that must be verified against source atoms. No heuristic or inference needed.

### 2. Numeric Extraction from Natural Language

**Current validator approach** (`validator.py`): regex extraction
```python
def extract_numbers(text: str) -> List[str]:
    pattern = r'\d[\d,]*\.?\d*'
    matches = re.findall(pattern, text)
    return [m.rstrip('.') for m in matches]
```

**This is sufficient for 12-A because:**
- Atoms are typically structured text (technical reports, metrics, facts)
- Numbers appear in clear form: "$10M", "1,000", "3.14", "2023"
- Edge case: "10 million" → not currently captured (future improvement)

**For derivation, we need to extract from atom content:**
1. Parse numbers from atom.content (use same extract_numbers)
2. For atoms with metadata, prefer metadata['numeric_value'] if present
3. Fall back to regex extraction from content text

### 3. Validator Extension for Derived Claims

**Current flow**: 
1. Extract citation [A###] from sentence
2. Look up atom content by citation_key
3. Check lexical overlap ≥2
4. Check numeric consistency (numbers in claim must appear in atom)

**Problem for derived claims**: 
- "Company A exceeded B by 25% [A001, A002]" cites two atoms
- Neither atom says "25%" individually
- Current validator looks for "25%" in either atom → WILL FAIL

**Solution in 12-A**: Before validator's numeric consistency check, detect if sentence expresses:
- A comparison between two cited entities
- A percentage, delta, or ranking claim

Then RECOMPUTE from cited atoms and verify:
```
derived = compute_from_atoms(cited_atoms, rule)
if abs(claimed_value - derived) > tolerance: FAIL
```

### 4. Deterministic Hashing for DerivedClaim ID

**Standard pattern**: SHA-256 of canonical (sorted) input string

```python
import hashlib
def make_claim_id(rule: str, atom_ids: List[str], version: str = "v1") -> str:
    raw = f"{rule}:{','.join(sorted(atom_ids))}:{version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

**Why 16-char truncation**: Full 64-char hash is verbose; 16 chars (8 bytes) gives ~10^19 possible IDs, sufficient for all practical atom combinations.

---

## Internal Codebase Analysis

### Integration Points Identified

**Where to insert derivation:**
```
assembler._build_from_context() line 160:
  collected.sort(key=...)  # Existing ranking or default sort
  
  <<< INSERT HERE >>>
  
  for atom_dict, atom_id in collected:  # Existing unpacking
      packet.atoms.append(atom_dict)
```

**EvidencePacket modification:**
Line 35-42 in assembler.py:
```python
@dataclass
class EvidencePacket:
    ...
    derived_claims: List[DerivedClaim] = field(default_factory=list)  # ADD THIS
```

### Existing Patterns to Follow

**ranking.py** (created in 12-07):
- `RankingConfig` dataclass with defaults
- `compute_composite_score()` pure function
- `apply_ranking()` pure function
- No side effects, deterministic

**derivation/engine.py should follow exactly:**
- `DerivationConfig` dataclass (optional, for tolerance/epsilon)
- `compute_delta()` pure function over 2 atoms
- `compute_percent_change()` pure function over 2 atoms  
- `compute_rank()` pure function over N atoms
- `DerivationEngine.run()` orchestrator

### Module Structure Decision

**Location**: `src/research/derivation/` (new module)

```
src/research/derivation/
├── __init__.py          # Exports DerivedClaim, DerivationEngine
├── engine.py            # Main engine + orchestration
└── rules.py             # Individual rule implementations
```

**vs single file**:
- Single file is simpler for 3 rules
- Module structure matches `reasoning/` pattern
- Decision: **single file** `src/research/derivation/engine.py` (enough for 12-A; can split later if needed)

### Test File Pattern

**Existing convention** from `test_ranking.py`:
```python
# Path setup
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_src = os.path.join(_project_root, "src")
for _p in [_src, _project_root]:
    if _p not in sys.path: sys.path.insert(0, _p)
```

**Helper function**:
```python
def make_item(atom_id, text, citation_key=None, metadata=None):
    meta = metadata or {}
    meta['atom_id'] = atom_id
    return RetrievedItem(
        content=text, source='test_source', strategy='semantic',
        knowledge_level='B', item_type='claim',
        relevance_score=0.9, citation_key=citation_key, metadata=meta
    )
```

### All Tests to Preserve

After 12-A implementation:
1. `tests/research/reasoning/test_ranking.py` (24 tests) — must pass
2. `tests/research/reasoning/test_phase11_invariants.py` (8 tests) — must pass
3. `tests/research/` full suite (39 tests) — must pass
4. **No regression in any existing test**

---

## Design Decisions from Research

### Decision 1: Storage Model
**Resolved**: Ephemeral on EvidencePacket. No persistence. Derived = projection, not truth.

### Decision 2: Citation Model
**Resolved**: Derived claims NOT separately cited. Writer cites [A001, A002] for derived statement. Derived claim is evidence-layer augmentation, not new citation type.

### Decision 3: Error Handling
**Resolved**: SKIP on failure. Never halt pipeline, never fabricate. Missing atoms → skip derivation. Non-numeric content → skip. Div-by-zero → skip.

### Decision 4: Determinism
**Resolved**: Sort input atoms by global_id. Pure functions. No randomness. SHA-256 ID from sorted inputs enables idempotence verification.

### Decision 5: Performance
**Resolved**: <1ms per rule. O(n log n) max. No async. Inline computation.

### Decision 6: Validator Extension
**Resolved**: Extend `validate_response_grounding()` to detect multi-atom numeric claims and recompute. FAIL if recomputed differs from claimed value beyond tolerance.

---

## Remaining Ambiguities

### 1. Validator Extension Scope
**Question**: Should validator also check derived claims from EvidencePacket directly, or only verify prose claims against atoms?

**Answer**: Verify prose claims ONLY. The validator receives `prose: str` and `retrieved_items: List[RetrievedItem]` — it does NOT have access to DerivedClaim objects. It must rederive inline from the cited atoms.

### 2. Numeric Extraction Robustness  
**Question**: Can we rely on regex for number extraction from atom content? What about "10 million" or "several thousand"?

**Answer**: For 12-A, only exact numeric matches (regex). "10 million" → skip derivation. Future phases can add structured metadata if needed.

### 3. Rank Output Format
**Question**: What does the `output` field of a rank derived claim contain?

**Answer**: `List[Tuple[str, float]]` — list of (atom_id, score) pairs, sorted descending. The highest-scoring atom is at index 0.

### 4. Delta/Percent: Which Atom Values?
**Question**: Atoms have numeric fields in content. How to find the "number" for delta? 

**Answer**: Use the FIRST numeric value found in each atom's content text. For delta/percent_change, require exactly 2 atoms. Extract first number from each, subtract.

### 5. Metadata Field for Derivation
**Question**: Atoms may have `metadata['numeric_value']` set during extraction. Should we prefer this over parsing content?

**Answer**: Yes — use metadata if present, otherwise parse from content. This is cleaner and more reliable.

---

## Kill Test Design

From user spec:

1. **Order Independence**: `shuffle(atoms) → output identical`
   - Implementation: call engine with shuffled vs sorted input, assert output.id and output.values match
   
2. **Mutation Sensitivity**: `change atom value → derived changes deterministically`  
   - Implementation: change A's value from 10 to 15, recompute, assert new output != old output
   
3. **Removal Failure**: `remove required atom → claim disappears`
   - Implementation: remove one of 2 required atoms, assert delta/percent_change claim is absent
   
4. **Validator Catch**: `inject incorrect claim → validator FAIL`
   - Implementation: write sentence with wrong percentage, call validator with correct atoms, assert is_valid=False

---

## Files Modified Summary (12-A)

| File | Action | Lines | Description |
|------|--------|-------|-------------|
| `src/research/derivation/__init__.py` | NEW | ~10 | Module init, export DerivedClaim, DerivationEngine |
| `src/research/derivation/engine.py` | NEW | ~200 | Engine + 3 rules (delta, percent, rank) |
| `src/research/reasoning/assembler.py` | MODIFY | ~5 lines added | Call engine, add derived_claims to EvidencePacket |
| `src/retrieval/validator.py` | MODIFY | ~20 lines added | Detect multi-atom numeric claims, recompute verify |
| `tests/research/derivation/test_engine.py` | NEW | ~150 | Full test suite: unit + kill tests |
| `.planning/phases/12-A/DERIVED_CLAIM_SCHEMA.md` | NEW | spec | Schema documentation |
| `.planning/phases/12-A/DERIVATION_RULES.md` | NEW | spec | Rule documentation |
| `.planning/phases/12-A/DERIVATION_VALIDATION.md` | NEW | spec | Validator extension documentation |

---

## Conclusion

Research complete. All integration points identified, ambiguities resolved. Ready to write PLAN.md.
