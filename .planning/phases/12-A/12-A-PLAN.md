---
phase: 12-A
plan: 01
type: tdd
depends_on:
  - 12-07  # ranking.py (rank rule integration)
files_modified:
  - src/research/derivation/__init__.py
  - src/research/derivation/engine.py
  - src/research/reasoning/assembler.py
  - src/retrieval/validator.py
  - tests/research/derivation/test_engine.py
autonomous: true
requirements:
  - DERIV-01  # delta rule
  - DERIV-02  # percent_change rule
  - DERIV-03  # rank rule
  - DERIV-04  # validator extension
  - DERIV-05  # determinism / kill tests
  - DERIV-06  # evidence packet integration

must_haves:
  truths:
    - "delta rule: given two atoms with numeric values, outputs their difference"
    - "percent_change rule: given two atoms, outputs ((new - old) / old) * 100"
    - "rank rule: given N atoms with numeric values, outputs sorted list of (atom_id, value)"
    - "All rules are pure functions: same inputs → same outputs, no LLM calls"
    - "derived_claims field added to EvidencePacket with deterministic ID"
    - "Derivation runs after ranking in _build_from_context, before unpacking to packet"
    - "SKIP on failure: missing atoms, non-numeric data, divide by zero → skip"
    - "Validator extension: detects multi-atom numeric claims, recomputes, verifies"
    - "Kill tests: order independence, mutation sensitivity, removal failure, validator catch"
    - "No regression: all existing tests (tests/research/) pass unchanged"
  artifacts:
    - path: "src/research/derivation/__init__.py"
      provides: "Module init, exports DerivedClaim, compute_delta, compute_percent_change, compute_rank, DerivationEngine"
    - path: "src/research/derivation/engine.py"
      provides: "DerivationEngine + rule implementations (delta, percent_change, rank)"
    - path: "tests/research/derivation/test_engine.py"
      provides: "Unit tests for all 3 rules + kill tests (order independence, mutation sensitivity, removal failure) + validator extension tests"
      exports:
        - test_delta_simple
        - test_delta_complex
        - test_delta_single_value
        - test_delta_no_numeric
        - test_percent_change_simple
        - test_percent_change_zero_old
        - test_percent_change_complex
        - test_rank_simple
        - test_rank_empty
        - test_rank_ties
        - test_deterministic_id
        - test_order_independence
        - test_mutation_sensitivity
        - test_removal_failure
        - test_integration_benchmark
        - test_validator_delta
        - test_validator_percent_change
        - test_validator_derived_fail
        - test_validator_source_only_still_passes
  key_links:
    - from: "src/research/derivation/engine.py"
      to: "src/research/reasoning/retriever.py"
      via: "from research.reasoning.retriever import RetrievedItem"
      pattern: "from research\\.reasoning\\.retriever import"
    - from: "src/research/reasoning/assembler.py"
      to: "src/research/derivation/engine.py"
      via: "from research.derivation.engine import DerivationEngine, DerivedClaim"
      pattern: "from research\\.derivation\\.engine import"
    - from: "src/research/reasoning/assembler.py"
      to: "src/research/derivation/engine.py"
      via: "EvidencePacket.derived_claims field"
      pattern: "derived_claims"
    - from: "src/retrieval/validator.py"
      to: "src/research/derivation/engine.py"
      via: "reimports: compute_delta, compute_percent_change, compute_rank"
      pattern: "from research\\.derivation\\.engine import"
---

<objective>
Implement the Derived Claim Engine: deterministic, LLM-free transformations that compute derived facts (delta, percent_change, rank) from retrieved knowledge atoms. Integrate into EvidenceAssembler, extend validator, and verify via comprehensive test suite including Nyquist kill tests.

Purpose: Add "insight layer" to evidence without breaking truth contract. Derived claims are provenance bound, purely deterministic, fully auditable.

Output:
- src/research/derivation/engine.py — pure function implementations
- src/research/reasoning/assembler.py — integration into _build_from_context
- src/retrieval/validator.py — extended validate_response_grounding
- tests/research/derivation/test_engine.py — full test suite (18+ tests)
- DERIVED_CLAIM_SCHEMA.md, DERIVATION_RULES.md, DERIVATION_VALIDATION.md — spec docs
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/plan-phase.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/12-A/12-A-CONTEXT.md
@.planning/phases/12-A/12-A-RESEARCH.md

<interfaces>
<!-- Contracts the executor needs -->

**EvidencePacket** (src/research/reasoning/assembler.py):
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
    # ADD THIS:
    derived_claims: List[DerivedClaim] = field(default_factory=list)
```

**RetrievedItem** (src/research/reasoning/retriever.py):
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

**DerivationConfig** (src/research/derivation/engine.py):
```python
@dataclass
class DerivationConfig:
    tolerance: float = 1e-9  # for floating-point comparison
    version: str = "12-A-v1"  # for deterministic ID generation
    extract_from_metadata: bool = True  # prefer metadata over content
```

**DerivedClaim** (src/research/derivation/engine.py):
```python
@dataclass(frozen=True)
class DerivedClaim:
    id: str                      # deterministic sha256[:16]
    rule: str                    # "delta" | "percent_change" | "rank"
    source_atom_ids: List[str]   # sorted, canonical
    output: Any                  # numeric or structured
    metadata: Dict[str, Any]     # rule-specific: {"atom_a_value": float, ...}
```

**DerivationEngine** (src/research/derivation/engine.py):
```python
class DerivationEngine:
    def __init__(self, config: DerivationConfig = None):
        self.config = config or DerivationConfig()
    
    def run(self, items: List[RetrievedItem]) -> List[DerivedClaim]:
        """Apply all derivation rules to sorted items. Returns derived claims."""
        # Sort by global_id for determinism
        sorted_items = sorted(items, key=lambda x: x.citation_key or '')
        claims = []
        for fn in [self._compute_all_deltas, self._compute_all_percents, self._compute_all_ranks]:
            try:
                claims.extend(fn(sorted_items))
            except:
                pass  # SKIP on failure
        return claims
    
    def _compute_all_deltas(self, items: List[RetrievedItem]) -> List[DerivedClaim]:
        """Find all pairs of atoms with numeric values, compute delta."""
    
    def _compute_all_percents(self, items: List[RetrievedItem]) -> List[DerivedClaim]:
        """Find all pairs of atoms with numeric values, compute percent change."""
    
    def _compute_all_ranks(self, items: List[RetrievedItem]) -> List[DerivedClaim]:
        """Rank all atoms by their numeric values."""
```

**Integration point** (src/research/reasoning/assembler.py, _build_from_context):
```python
# AFTER line 160 (ranking/default sort):
from research.derivation.engine import DerivationEngine
derived = DerivationEngine().run(items_parallel)
```

**Existing validator** (src/retrieval/validator.py):
- `validate_response_grounding(response_text, retrieved_items)` — current version
- New requirement: detect multi-atom numeric claims, recompute, verify

**Test helper** (from test_phase11_invariants.py):
```python
def make_retrieved_item(atom_id, text, citation_key=None, metadata=None):
    meta = metadata or {'atom_id': atom_id, 'citation_key': citation_key}
    return RetrievedItem(
        content=text, source='test_source', strategy='semantic',
        knowledge_level='B', item_type='claim',
        relevance_score=0.9, citation_key=citation_key, metadata=meta
    )
```
</interfaces>
</context>

<feature>
  <name>Derived Claim Engine</name>
  <files>
    src/research/derivation/__init__.py
    src/research/derivation/engine.py
    tests/research/derivation/test_engine.py
  </files>
  <behavior>
    RED phase — write tests first, then implement:

    1. test_delta_simple: Create two RetrievedItems with numeric metadata (A=10, B=7). Call compute_delta. assert result = 3.0
    2. test_delta_complex: Create items with complex text ("Revenue of $1,200"). Verify regex extracts 1200 correctly. assert delta = extracted_a - extracted_b
    3. test_delta_no_numeric: Create items without numbers. assert result is empty list
    4. test_percent_change_simple: A=80, B=100. assert percent_change = -20.0
    5. test_percent_change_zero_old: A=50, B=0. assert result is empty list (skip, not fail)
    6. test_rank_simple: Create three items with values 10, 30, 20. assert output = [(B,30), (C,20), (A,10)]
    7. test_rank_ties: Two items with same value. assert tie broken by citation_key ascending
    8. test_deterministic_id: Call engine twice with identical input. assert all claim IDs equal
    9. test_order_independence: Shuffle input list, call engine again. assert output IDs match original order
    10. test_mutation_sensitivity: Change atom A's value from 10 to 20. assert new output ≠ old output
    11. test_removal_failure: Remove atom B from input. assert delta/percent_claims referencing B are absent
    12. test_validator_delta: Write sentence "B exceeds A by 3 [A001, A002]" (A=7, B=10). assert validator passes
    13. test_validator_percent_change: Write sentence "B is 25% less than A [A001, A002]" (A=100, B=75). assert validator passes
    14. test_validator_derived_fail: Write sentence "B exceeds A by 50 [A001, A002]" (A=10, B=7). assert validator FAILS
    15. test_validator_source_only_still_passes: Write sentence citing single atom with matching content. assert validator passes
    16. test_integration_benchmark: Full pipeline call through DerivationEngine.run() with 5 items. assert output has correct count of derived claims

    GREEN: implement engine.py with 3 rules (delta, percent, rank)
    REFACTOR: ensure test helpers shared, remove duplication

    Integration tests:
    17. test_evidence_assembler_integration: Mock retriever, call assemble_all_sections. assert packet has derived_claims
    18. test_no_regression: Run tests/research/ suite. assert 0 failures
  </behavior>
</feature>

<implementation>
  Follow RED→GREEN→REFACTOR:

  RED: Write all tests above into tests/research/derivation/test_engine.py. Run tests, confirm they fail for right reasons.

  GREEN: Implement src/research/derivation/engine.py with:
    1. DerivedClaim dataclass (frozen=True, deterministic ID)
    2. DerivationConfig dataclass (tolerance, version, extract_from_metadata)
    3. compute_delta(atom_a, atom_b, config) -> float
    4. compute_percent_change(atom_a, atom_b, config) -> float
    5. compute_rank(atoms, config) -> List[Tuple[str, float]]
    6. DerivationEngine.run(items) -> List[DerivedClaim]

  Integration:
    7. Modify EvidencePacket dataclass: add derived_claims field
    8. Modify _build_from_context: call DerivationEngine().run(), attach to packet
    9. Modify validator.py: detect derived numeric claims, recompute, verify

  REFACTOR:
    10. Extract shared test helper (make_item)
    11. Extract numeric value helper (_extract_numeric_value)
    12. Remove debug print statements
</implementation>

<verification>
  <automated>cd /home/bamn/Sheppard && python -m pytest tests/research/derivation/test_engine.py -v</automated>
  <automated>cd /home/bamn/Sheppard && python -m pytest tests/research/ -x -q</automated>
  <automated>cd /home/bamn/Sheppard && python -c "from research.derivation.engine import DerivedClaim, DerivationEngine, compute_delta; print('Import OK')"</automated>
</verification>

<success_criteria>
- src/research/derivation/engine.py exists with DerivedClaim, DerivationEngine, compute_delta, compute_percent_change, compute_rank
- tests/research/derivation/test_engine.py exists with at least 16 tests covering all 3 rules, determinism, kill tests, and validator extension
- `python -m pytest tests/research/derivation/test_engine.py -v` succeeds with all tests green
- `python -m pytest tests/research/ -x -q` succeeds with no regressions (existing 39+ tests pass)
- EvidencePacket has derived_claims field
- EvidenceAssembler._build_from_context calls DerivationEngine and attaches results
- Validator extended to verify derived numeric claims (recomputes and validates)
- No LLM calls in derivation module (enforced by grep/assert)
- Deterministic outputs: same input → same output (verified by kill tests)
</success_criteria>

<output>
After completion, create `.planning/phases/12-A/12-A-SUMMARY.md`
</output>
