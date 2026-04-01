---
phase: 12-A
plan: 02
type: tdd
wave: 1
depends_on: []
files_modified:
  - src/research/derivation/engine.py
  - src/research/derivation/__init__.py
  - tests/research/derivation/test_engine_expansion.py
autonomous: true
requirements:
  - DERIV-EXP-01
  - DERIV-EXP-02
  - DERIV-EXP-03
  - DERIV-EXP-04
  - DERIV-EXP-05

must_haves:
  truths:
    - "compute_ratio(A, B) returns A/B as a DerivedClaim; returns None when B=0 or no numerics"
    - "compute_chronology orders atoms by publish_date (falling back to recency_days) and emits (earliest_id, latest_id, delta_seconds); returns None with fewer than 2 atoms"
    - "compute_support_rollup groups atoms by entity_id/concept_name metadata, emitting a count claim only when count >= 2; deduplicates by citation_key"
    - "compute_conflict_rollup counts atoms where is_contradiction=True in metadata, grouped by concept_name; returns None when zero contradiction atoms"
    - "DerivationEngine.run() calls all 7 rules (3 existing + 4 new) and all 14 expansion tests pass"
    - "All 27 prior tests (18 engine + 9 validator) continue to pass after expansion — zero regressions"
    - "compute_ratio, compute_chronology, compute_support_rollup, compute_conflict_rollup are exported from src/research/derivation/__init__.py"
  artifacts:
    - path: "tests/research/derivation/test_engine_expansion.py"
      provides: "14 TDD tests for new derivation rules"
      min_lines: 150
    - path: "src/research/derivation/engine.py"
      provides: "4 new rule functions + updated DerivationEngine.run()"
      contains: "def compute_ratio"
    - path: "src/research/derivation/__init__.py"
      provides: "Updated exports"
      exports:
        - compute_ratio
        - compute_chronology
        - compute_support_rollup
        - compute_conflict_rollup
  key_links:
    - from: "DerivationEngine.run()"
      to: "compute_ratio, compute_chronology, compute_support_rollup, compute_conflict_rollup"
      via: "try/except blocks (skip-on-failure pattern)"
      pattern: "compute_ratio|compute_chronology|compute_support_rollup|compute_conflict_rollup"
    - from: "compute_chronology"
      to: "dateutil.parser.parse"
      via: "publish_date metadata field"
      pattern: "dateutil"
    - from: "src/research/derivation/__init__.py"
      to: "compute_ratio, compute_chronology, compute_support_rollup, compute_conflict_rollup"
      via: "explicit imports from engine"
      pattern: "compute_ratio"
---

<objective>
Expand the Derived Claim Engine with 4 new deterministic rules: ratio, chronology, simple_support_rollup, and simple_conflict_rollup. All rules follow the existing skip-on-failure, no-LLM, deterministic-ID contract established in Phase 12-A.

Purpose: The engine currently handles numeric comparison (delta, percent_change) and ordering (rank). The expansion adds division relationships (ratio), temporal ordering (chronology), and metadata-driven grouping (support/conflict rollups) — rounding out the rule set needed for downstream claim graph construction in Phase 12-C.

Output: 14 new passing tests in test_engine_expansion.py, 4 new rule functions in engine.py, updated DerivationEngine.run() calling all 7 rules, updated __init__.py exports.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md

<!-- Key source files the executor needs directly — no codebase exploration required -->
</context>

<interfaces>
<!-- Extracted from src/research/derivation/engine.py — executor uses these directly -->

Existing helpers available in engine.py:

```python
# Numeric extraction
def _extract_numeric_value(item: RetrievedItem, from_metadata: bool = True) -> Optional[float]: ...
    # Priority: metadata['numeric_value'] → first regex number in content → None

# Deterministic ID generation
def make_claim_id(rule: str, atom_ids: List[str], version: str = CONFIG_VERSION) -> str: ...
    # sha256(f"{rule}:{','.join(sorted(atom_ids))}:{version}")[:16]

CONFIG_VERSION = "12-A-v1"  # Use for new rules too

# Frozen dataclass — do not mutate after construction
@dataclass(frozen=True)
class DerivedClaim:
    id: str
    rule: str
    source_atom_ids: List[str]  # sorted, canonical
    output: Any
    metadata: Dict[str, Any]
```

RetrievedItem fields used by new rules:
```python
# From research.reasoning.retriever import RetrievedItem
item.citation_key     # str | None — primary atom identifier
item.metadata         # Dict[str, Any] | None
item.content          # str — raw text

# Metadata keys used by new rules:
item.metadata.get('numeric_value')    # float — for ratio (via _extract_numeric_value)
item.metadata.get('publish_date')     # str — ISO date string, used by chronology
item.metadata.get('recency_days')     # int/float — fallback for chronology (higher = older)
item.metadata.get('entity_id')        # str — grouping key for support_rollup
item.metadata.get('concept_name')     # str — grouping key for support_rollup AND conflict_rollup
item.metadata.get('is_contradiction') # bool — filter for conflict_rollup
```

DerivationEngine.run() pattern — wrap each new rule block identically to existing ones:
```python
try:
    ratio_claims = self._compute_all_ratios(sorted_items)
    claims.extend(ratio_claims)
except Exception as e:
    logger.debug(f"[DerivationEngine] Ratio computation failed: {e}")
```
</interfaces>

<tasks>

<task type="tdd">
  <name>Task 1 (RED): Write 14 failing tests for new derivation rules</name>
  <files>tests/research/derivation/test_engine_expansion.py</files>
  <behavior>
    Implement exactly these 14 test functions. Each must FAIL before Task 2 because the functions under test do not yet exist. Run the test file after writing to confirm all 14 fail with ImportError or AttributeError.

    File header (copy verbatim for sys.path setup):
    ```python
    import sys, os
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    _src = os.path.join(_project_root, "src")
    for _p in [_src, _project_root]:
        if _p not in sys.path:
            sys.path.insert(0, _p)
    ```

    Import target (will fail RED until Task 2):
    ```python
    from research.derivation.engine import (
        compute_ratio,
        compute_chronology,
        compute_support_rollup,
        compute_conflict_rollup,
        DerivationEngine,
        DerivedClaim,
        make_claim_id,
    )
    ```

    Use the same make_item() helper pattern as test_engine.py:
    ```python
    def make_item(atom_id=None, text="", citation_key=None, metadata=None):
        from research.reasoning.retriever import RetrievedItem
        meta = metadata or {}
        if atom_id:
            meta['atom_id'] = atom_id
        return RetrievedItem(
            content=text, source='test_source', strategy='test',
            knowledge_level='B', item_type='claim',
            citation_key=citation_key or atom_id, metadata=meta
        )
    ```

    Test 1 — test_ratio_simple:
      atom_a = make_item(citation_key='A', metadata={'numeric_value': 10.0})
      atom_b = make_item(citation_key='B', metadata={'numeric_value': 4.0})
      claim = compute_ratio(atom_a, atom_b)
      assert claim is not None
      assert claim.rule == "ratio"
      assert abs(claim.output - 2.5) < 1e-9
      assert sorted(claim.source_atom_ids) == ['A', 'B']

    Test 2 — test_ratio_zero_denominator:
      atom_a = make_item(citation_key='A', metadata={'numeric_value': 10.0})
      atom_b = make_item(citation_key='B', metadata={'numeric_value': 0.0})
      claim = compute_ratio(atom_a, atom_b)
      assert claim is None  # zero-division guard

    Test 3 — test_ratio_no_numeric:
      atom_a = make_item(citation_key='A', text='just text, no numbers')
      atom_b = make_item(citation_key='B', text='also no numbers here')
      claim = compute_ratio(atom_a, atom_b)
      assert claim is None

    Test 4 — test_chronology_by_publish_date:
      Items with publish_date in metadata (ISO strings). Executor must verify:
        atom_a = make_item(citation_key='A', metadata={'publish_date': '2023-01-01'})
        atom_b = make_item(citation_key='B', metadata={'publish_date': '2023-06-15'})
        atom_c = make_item(citation_key='C', metadata={'publish_date': '2024-03-20'})
      claim = compute_chronology([atom_a, atom_b, atom_c])
      assert claim is not None
      assert claim.rule == "chronology"
      assert claim.output['earliest_id'] == 'A'
      assert claim.output['latest_id'] == 'C'
      assert claim.output['delta_seconds'] > 0

    Test 5 — test_chronology_fallback_recency_days:
      No publish_date, use recency_days (higher = older, i.e., published further in the past):
        atom_a = make_item(citation_key='A', metadata={'recency_days': 365})  # older
        atom_b = make_item(citation_key='B', metadata={'recency_days': 30})   # newer
      claim = compute_chronology([atom_a, atom_b])
      assert claim is not None
      assert claim.output['earliest_id'] == 'A'   # higher recency_days = older = earliest
      assert claim.output['latest_id'] == 'B'

    Test 6 — test_chronology_single_atom:
      Only 1 atom → need at least 2 to establish chronology:
        atom_a = make_item(citation_key='A', metadata={'publish_date': '2023-01-01'})
      claim = compute_chronology([atom_a])
      assert claim is None

    Test 7 — test_support_rollup_basic:
      3 atoms, 2 share concept_name="Python", 1 has concept_name="Java":
        atom_a = make_item(citation_key='A', metadata={'concept_name': 'Python'})
        atom_b = make_item(citation_key='B', metadata={'concept_name': 'Python'})
        atom_c = make_item(citation_key='C', metadata={'concept_name': 'Java'})
      claim = compute_support_rollup([atom_a, atom_b, atom_c])
      assert claim is not None
      assert claim.rule == "simple_support_rollup"
      rollup = claim.output  # dict: {entity_name: count}
      assert rollup.get('Python') == 2
      assert 'Java' not in rollup  # below threshold of 2

    Test 8 — test_support_rollup_dedup:
      Same citation_key twice → counted only once:
        atom_a = make_item(citation_key='A', metadata={'concept_name': 'Python'})
        atom_dup = make_item(citation_key='A', metadata={'concept_name': 'Python'})  # same citation_key
        atom_b = make_item(citation_key='B', metadata={'concept_name': 'Python'})
      claim = compute_support_rollup([atom_a, atom_dup, atom_b])
      assert claim is not None
      assert claim.output.get('Python') == 2  # A counted once, B counted once

    Test 9 — test_support_rollup_below_threshold:
      Every entity appears only once → no claim emitted:
        atom_a = make_item(citation_key='A', metadata={'concept_name': 'Python'})
        atom_b = make_item(citation_key='B', metadata={'concept_name': 'Java'})
      claim = compute_support_rollup([atom_a, atom_b])
      assert claim is None  # nothing meets count >= 2

    Test 10 — test_conflict_rollup_basic:
      2 atoms with is_contradiction=True:
        atom_a = make_item(citation_key='A', metadata={'is_contradiction': True, 'concept_name': 'revenue'})
        atom_b = make_item(citation_key='B', metadata={'is_contradiction': True, 'concept_name': 'revenue'})
        atom_c = make_item(citation_key='C', metadata={'is_contradiction': False, 'concept_name': 'revenue'})
      claim = compute_conflict_rollup([atom_a, atom_b, atom_c])
      assert claim is not None
      assert claim.rule == "simple_conflict_rollup"
      assert claim.output.get('revenue') == 2

    Test 11 — test_conflict_rollup_none:
      Zero contradiction atoms → return None:
        atom_a = make_item(citation_key='A', metadata={'is_contradiction': False, 'concept_name': 'revenue'})
        atom_b = make_item(citation_key='B', metadata={'concept_name': 'revenue'})  # no is_contradiction key
      claim = compute_conflict_rollup([atom_a, atom_b])
      assert claim is None

    Test 12 — test_engine_run_includes_new_rules:
      Engine.run() output should contain ratio and support_rollup claims when inputs qualify:
        items = [
          make_item(citation_key='A', metadata={'numeric_value': 10.0, 'concept_name': 'ML'}),
          make_item(citation_key='B', metadata={'numeric_value': 4.0, 'concept_name': 'ML'}),
          make_item(citation_key='C', metadata={'numeric_value': 5.0, 'concept_name': 'ML'}),
        ]
      engine = DerivationEngine()
      claims = engine.run(items)
      rules = {c.rule for c in claims}
      assert 'ratio' in rules
      assert 'simple_support_rollup' in rules

    Test 13 — test_no_regression:
      Run existing test suite as subprocess to confirm 0 failures:
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, '-m', 'pytest',
             'tests/research/derivation/test_engine.py',
             'tests/retrieval/test_validator_derived.py',
             '-x', '-q', '--tb=short'],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), '..', '..', '..')
        )
        assert result.returncode == 0, f"Regression detected:\n{result.stdout}\n{result.stderr}"

    Test 14 — test_determinism_new_rules:
      Call engine twice on same input; claim IDs must be identical:
        items = [
          make_item(citation_key='X', metadata={'numeric_value': 8.0, 'concept_name': 'AI'}),
          make_item(citation_key='Y', metadata={'numeric_value': 2.0, 'concept_name': 'AI'}),
        ]
      engine = DerivationEngine()
      claims1 = engine.run(items)
      claims2 = engine.run(items)
      ids1 = sorted(c.id for c in claims1)
      ids2 = sorted(c.id for c in claims2)
      assert ids1 == ids2
  </behavior>
  <action>
    Create /home/bamn/Sheppard/tests/research/derivation/test_engine_expansion.py with exactly the 14 tests described in the behavior block.

    After writing: run `cd /home/bamn/Sheppard && python -m pytest tests/research/derivation/test_engine_expansion.py -x -q 2>&1 | head -20` to confirm it fails with ImportError (all 14 tests collected, all fail RED due to missing functions).

    Do NOT implement engine.py yet — this is the RED step.

    Commit with message: `test(12-A): add 14 failing expansion tests for ratio/chronology/rollup rules`
  </action>
  <verify>
    <automated>cd /home/bamn/Sheppard && python -m pytest tests/research/derivation/test_engine_expansion.py --collect-only -q 2>&1 | tail -5</automated>
  </verify>
  <done>14 tests collected, all fail (ImportError or AttributeError on compute_ratio etc.). No syntax errors in test file.</done>
</task>

<task type="tdd">
  <name>Task 2 (GREEN): Implement 4 new rules in engine.py + update __init__.py</name>
  <files>src/research/derivation/engine.py, src/research/derivation/__init__.py</files>
  <behavior>
    Add 4 functions to engine.py (after existing rules, before DerivationEngine class). Then add 4 private helper methods to DerivationEngine and wire them into run(). Then update __init__.py exports.

    RULE 1: compute_ratio
    - Signature: compute_ratio(atom_a, atom_b, config=None) -> Optional[DerivedClaim]
    - Use _extract_numeric_value for both atoms (same as compute_delta)
    - Guard: if val_b is None or val_b == 0.0: return None
    - Guard: if val_a is None: return None
    - result = val_a / val_b
    - id_a = atom_a.citation_key or atom_a.metadata.get('atom_id', '')
    - id_b = atom_b.citation_key or atom_b.metadata.get('atom_id', '')
    - claim_id = make_claim_id("ratio", [id_a, id_b], ...)
    - output: result (float)
    - metadata: {"atom_a_id": id_a, "atom_b_id": id_b, "atom_a_value": val_a, "atom_b_value": val_b, "formula": "A / B"}

    RULE 2: compute_chronology
    - Signature: compute_chronology(atoms, config=None) -> Optional[DerivedClaim]
    - Import at function body top: from dateutil import parser as dateutil_parser (avoid module-level import)
    - Deduplicate input by citation_key before processing
    - Build list of (atom_id, timestamp_float) pairs:
      - For each atom: try metadata['publish_date'] → dateutil_parser.parse(publish_date).timestamp()
      - If publish_date absent or unparseable: try metadata['recency_days'] → use as negative offset from epoch (higher recency_days = older = smaller timestamp). Use: timestamp = -float(recency_days)
      - If neither present: skip that atom
    - If fewer than 2 atoms have timestamps: return None
    - Sort by timestamp ascending → earliest (smallest timestamp), latest (largest timestamp)
    - earliest_id = first in sorted list; latest_id = last in sorted list
    - delta_seconds = latest_timestamp - earliest_timestamp (for recency_days fallback this will be a negative-based delta; that is acceptable — just use abs() for the delta)
    - Actually delta_seconds = abs(latest_timestamp - earliest_timestamp)
    - all_ids = sorted([pair[0] for pair in timestamped_atoms])
    - claim_id = make_claim_id("chronology", all_ids, ...)
    - output: {"earliest_id": earliest_id, "latest_id": latest_id, "delta_seconds": delta_seconds}
    - metadata: {"atom_count": len(timestamped_atoms), "sort_key_used": "publish_date or recency_days"}

    RULE 3: compute_support_rollup
    - Signature: compute_support_rollup(atoms, config=None) -> Optional[DerivedClaim]
    - from collections import defaultdict
    - Deduplicate by citation_key first: seen_keys = set(); deduped = []
    - Group by entity key: for each atom, key = metadata.get('entity_id') or metadata.get('concept_name'); if key is None: skip
    - Use defaultdict(set): groups[key].add(atom_id) — use sets so duplicates are automatically excluded
    - Actually: after dedup by citation_key, use defaultdict(int): groups[key] += 1
    - Filter: only keep groups where count >= 2
    - If no groups meet threshold: return None
    - output: dict of {entity_key: count} for all groups with count >= 2
    - all_ids = sorted(atom_id for atom in deduped atoms that contributed to any qualifying group)
    - claim_id = make_claim_id("simple_support_rollup", all_ids, ...)
    - metadata: {"threshold": 2, "total_entities_found": len(all_groups_before_filter)}

    RULE 4: compute_conflict_rollup
    - Signature: compute_conflict_rollup(atoms, config=None) -> Optional[DerivedClaim]
    - Filter atoms where metadata.get('is_contradiction') is True (strict boolean check)
    - If zero such atoms: return None
    - Group by metadata.get('concept_name', 'unknown')
    - output: dict of {concept_name: count}
    - all_ids = sorted(atom.citation_key or atom.metadata.get('atom_id','') for filtered atoms)
    - claim_id = make_claim_id("simple_conflict_rollup", all_ids, ...)
    - metadata: {"total_contradictions": sum of all counts}

    DerivationEngine updates:

    Add to run() (wrap each in try/except per existing pattern):
    ```python
    try:
        ratio_claims = self._compute_all_ratios(sorted_items)
        claims.extend(ratio_claims)
    except Exception as e:
        logger.debug(f"[DerivationEngine] Ratio computation failed: {e}")

    try:
        chron_claim = self._compute_chronology(sorted_items)
        if chron_claim is not None:
            claims.append(chron_claim)
    except Exception as e:
        logger.debug(f"[DerivationEngine] Chronology computation failed: {e}")

    try:
        support_claim = self._compute_support_rollup(sorted_items)
        if support_claim is not None:
            claims.append(support_claim)
    except Exception as e:
        logger.debug(f"[DerivationEngine] Support rollup computation failed: {e}")

    try:
        conflict_claim = self._compute_conflict_rollup(sorted_items)
        if conflict_claim is not None:
            claims.append(conflict_claim)
    except Exception as e:
        logger.debug(f"[DerivationEngine] Conflict rollup computation failed: {e}")
    ```

    Add private helpers:
    - _compute_all_ratios: same pair-iteration pattern as _compute_all_deltas, calling compute_ratio
    - _compute_chronology: calls compute_chronology(items, self.config)
    - _compute_support_rollup: calls compute_support_rollup(items, self.config)
    - _compute_conflict_rollup: calls compute_conflict_rollup(items, self.config)

    __init__.py: Add the 4 new names to both the import line and __all__.

    Update module docstring in engine.py to include the 4 new rules in the list.
  </behavior>
  <action>
    Edit /home/bamn/Sheppard/src/research/derivation/engine.py: add the 4 new functions and update DerivationEngine.

    Edit /home/bamn/Sheppard/src/research/derivation/__init__.py: add 4 new exports.

    After each file edit, run the test suite to verify GREEN:
      cd /home/bamn/Sheppard && python -m pytest tests/research/derivation/test_engine_expansion.py -x -q

    Once all 14 pass, run the full regression check:
      cd /home/bamn/Sheppard && python -m pytest tests/research/derivation/ tests/retrieval/test_validator_derived.py -x -q

    Confirm export import works:
      cd /home/bamn/Sheppard && python -c "from research.derivation.engine import compute_ratio, compute_chronology, compute_support_rollup, compute_conflict_rollup; print('Exports OK')"

    Commit with message: `feat(12-A): implement ratio, chronology, support_rollup, conflict_rollup rules`
  </action>
  <verify>
    <automated>cd /home/bamn/Sheppard && python -m pytest tests/research/derivation/test_engine_expansion.py -v --tb=short 2>&1 | tail -20</automated>
  </verify>
  <done>All 14 expansion tests pass. All 27 prior tests still pass. Export import command prints "Exports OK".</done>
</task>

<task type="auto">
  <name>Task 3 (REFACTOR + SUMMARY): Clean up and document</name>
  <files>
    src/research/derivation/engine.py,
    .planning/phases/12-A/12-A-SUMMARY.md
  </files>
  <action>
    Refactor engine.py (keep all tests green throughout):
    - Ensure module-level docstring lists all 7 rules (delta, percent_change, rank, ratio, chronology, simple_support_rollup, simple_conflict_rollup)
    - Ensure CONFIG_VERSION remains "12-A-v1" (do not bump — same version used for all IDs)
    - Verify dateutil import is inside compute_chronology function body (not at module level), to avoid hard dependency at import time for callers that never use chronology
    - Verify all 4 new functions have docstrings matching the style of compute_delta (formula, returns None conditions, determinism note)
    - Run full suite one final time:
        cd /home/bamn/Sheppard && python -m pytest tests/research/derivation/ tests/retrieval/test_validator_derived.py -x -q

    Create .planning/phases/12-A/12-A-SUMMARY.md with the following content structure:
    ```
    # Phase 12-A Summary — Derived Claim Engine (Full)

    ## Status: COMPLETE

    ## What Was Built
    [List all files created/modified with brief description]

    ## Rules Implemented (Total: 7)
    [Table: rule name, function, output type, skip condition]

    ## Test Coverage
    - tests/research/derivation/test_engine.py: 18 tests (original, all passing)
    - tests/research/derivation/test_engine_expansion.py: 14 tests (new, all passing)
    - tests/retrieval/test_validator_derived.py: 9 tests (dual validator, all passing)
    - Total: 41 tests, 0 failures

    ## Key Design Decisions
    [3-5 bullets on: skip-on-failure, deterministic IDs, no-LLM, dateutil placement, etc.]

    ## Export Interface
    [List all exported symbols from __init__.py]

    ## Next Phase
    12-B is complete (dual validator). 12-C (Claim Graph Builder) is next.
    ```

    Commit with message: `docs(12-A): refactor engine docstrings + create 12-A-SUMMARY.md`
  </action>
  <verify>
    <automated>cd /home/bamn/Sheppard && python -m pytest tests/research/derivation/ tests/retrieval/test_validator_derived.py -q 2>&1 | tail -5</automated>
  </verify>
  <done>
    - All 41 tests pass (18 original + 14 expansion + 9 validator)
    - engine.py docstring lists all 7 rules
    - 12-A-SUMMARY.md exists at .planning/phases/12-A/12-A-SUMMARY.md
    - dateutil import is local to compute_chronology (not module-level)
    - 3 commits created (RED, GREEN, REFACTOR)
  </done>
</task>

</tasks>

<verification>
Run all three verification commands in order:

```bash
# 1. New expansion tests
cd /home/bamn/Sheppard && python -m pytest tests/research/derivation/test_engine_expansion.py -v

# 2. Full regression check (41 tests total)
cd /home/bamn/Sheppard && python -m pytest tests/research/derivation/ tests/retrieval/test_validator_derived.py -x -q

# 3. Export smoke test
cd /home/bamn/Sheppard && python -c "from research.derivation.engine import compute_ratio, compute_chronology, compute_support_rollup, compute_conflict_rollup; print('Exports OK')"
```

All three must succeed with zero failures.
</verification>

<success_criteria>
- tests/research/derivation/test_engine_expansion.py exists with exactly 14 tests, all passing
- python -m pytest tests/research/derivation/ tests/retrieval/test_validator_derived.py -x -q → 41 passed, 0 failed
- python -c "from research.derivation.engine import compute_ratio, compute_chronology, compute_support_rollup, compute_conflict_rollup; print('Exports OK')" → prints "Exports OK"
- DerivationEngine.run() has 7 rule invocations (3 original + 4 new), each wrapped in try/except
- No LLM calls anywhere in src/research/derivation/ (confirmed by: grep -r "anthropic\|openai\|llm\|LLM" src/research/derivation/ → no matches)
- 12-A-SUMMARY.md committed to .planning/phases/12-A/
</success_criteria>

<output>
After completion, create `.planning/phases/12-A/12-A-SUMMARY.md` as described in Task 3.
</output>
