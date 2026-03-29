---
phase: 05a-dedup
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/research/condensation/pipeline.py
  - tests/test_atom_dedup.py
autonomous: true
requirements: [A11]
gap_closure: true

must_haves:
  truths:
    - "Re-running distillation on the same (mission_id, source_id, content) triple yields the same atom_id"
    - "The ON CONFLICT path in store_atom_with_evidence fires on the second run, updating rather than inserting"
    - "Atom count in knowledge.knowledge_atoms does not increase on re-run of identical input"
  artifacts:
    - path: "src/research/condensation/pipeline.py"
      provides: "Deterministic uuid5 atom_id derivation replacing uuid4"
      contains: "uuid.uuid5(uuid.NAMESPACE_URL"
    - path: "tests/test_atom_dedup.py"
      provides: "Automated verification that the same input yields the same atom_id"
      exports: ["test_atom_id_is_deterministic", "test_different_content_gives_different_id"]
  key_links:
    - from: "pipeline.py:89"
      to: "storage_adapter.py ON CONFLICT atom_id"
      via: "stable atom_id derived from content hash"
      pattern: "uuid\\.uuid5\\(uuid\\.NAMESPACE_URL"
---

<objective>
Close gap A11: atom_id is currently generated with uuid.uuid4() on every extraction pass, so the ON CONFLICT (atom_id) clause in store_atom_with_evidence never fires and duplicate atoms accumulate for identical content.

Purpose: Make atom storage idempotent so re-running distillation on the same source cannot create duplicate logical atoms.
Output: Modified pipeline.py with deterministic atom_id, plus a pytest module verifying the property.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/gauntlet_phases/phase05a_dedup/PHASE-05A-PLAN.md

<interfaces>
<!-- From src/research/condensation/pipeline.py (lines 56–116) -->
<!-- uuid is imported inline at line 56: `import uuid` -->
<!-- atom_id is constructed at line 89 and passed into KnowledgeAtom at line 93 -->
<!-- source_id is available as a local variable at line 74 -->
<!-- mission_id is the outer function argument -->
<!-- atom_dict is the loop variable; atom_dict.get('content', '') is the atom text -->

From src/memory/storage_adapter.py (store_atom_with_evidence):
```python
async def store_atom_with_evidence(self, atom: JsonDict, evidence_rows: Sequence[JsonDict]) -> None:
    # key_fields = ["atom_id"]
    # ON CONFLICT (atom_id) DO UPDATE SET ... (fires when atom_id already exists)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Replace uuid4 with deterministic uuid5 in pipeline.py</name>
  <files>src/research/condensation/pipeline.py</files>
  <read_first>
    - src/research/condensation/pipeline.py (lines 56–120) — understand the loop, local variables available (mission_id, source_id, atom_dict), and the inline `import uuid` at line 56
  </read_first>
  <behavior>
    - Same (mission_id, source_id, content[:200]) triple always produces the same atom_id
    - Different content strings produce different atom_ids
    - Empty content string is handled gracefully (uuid5 of empty string is still deterministic)
  </behavior>
  <action>
At line 89 of src/research/condensation/pipeline.py, replace:

    atom_id = str(uuid.uuid4())

with:

    atom_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{source_id}:{atom_dict.get('content', '')[:200]}"))

No other lines change. The `import uuid` already exists at line 56 and covers both uuid4 and uuid5. No schema change is required — atom_id remains a UUID column.

This ensures that for any given (mission, source, content-prefix) triple the atom_id is identical across pipeline runs, so the existing `ON CONFLICT (atom_id) DO UPDATE` in storage_adapter.py will fire on re-runs and update rather than insert a duplicate row.
  </action>
  <verify>
    <automated>grep -n "uuid.uuid5(uuid.NAMESPACE_URL" /home/bamn/Sheppard/src/research/condensation/pipeline.py</automated>
  </verify>
  <done>
    Line 89 of pipeline.py reads `atom_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{source_id}:{atom_dict.get('content', '')[:200]}"))` and no occurrence of `uuid.uuid4()` remains in that file.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Write pytest module verifying deterministic atom_id behavior</name>
  <files>tests/test_atom_dedup.py</files>
  <read_first>
    - src/research/condensation/pipeline.py (lines 56–120) — confirm final form of the uuid5 expression after Task 1 is applied, to mirror it exactly in the test
  </read_first>
  <behavior>
    - test_atom_id_is_deterministic: calling the uuid5 expression twice with identical inputs returns the same string
    - test_different_content_gives_different_id: two different content strings produce two different atom_ids
    - test_empty_content_is_stable: empty content string produces a consistent atom_id (no crash, same value on repeat)
    - test_uuid4_is_not_used: uuid4 is absent from pipeline.py (grep-based assertion)
  </behavior>
  <action>
Create /home/bamn/Sheppard/tests/test_atom_dedup.py with the following content (no external imports beyond stdlib and pytest):

```python
"""
tests/test_atom_dedup.py

Verifies that atom_id derivation in condensation/pipeline.py is deterministic,
closing gap A11 (duplicate atoms on re-run).
"""
import uuid
import subprocess
import sys
from pathlib import Path

PIPELINE_PATH = Path(__file__).parent.parent / "src" / "research" / "condensation" / "pipeline.py"


def _derive_atom_id(mission_id: str, source_id: str, content: str) -> str:
    """Mirror of the expression in pipeline.py line 89."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{source_id}:{content[:200]}"))


def test_atom_id_is_deterministic():
    id1 = _derive_atom_id("mission-1", "source-1", "Neural scaling laws show...")
    id2 = _derive_atom_id("mission-1", "source-1", "Neural scaling laws show...")
    assert id1 == id2, "Same inputs must yield the same atom_id"


def test_different_content_gives_different_id():
    id1 = _derive_atom_id("mission-1", "source-1", "Transformers use attention")
    id2 = _derive_atom_id("mission-1", "source-1", "Diffusion models use noise")
    assert id1 != id2, "Different content must yield different atom_ids"


def test_empty_content_is_stable():
    id1 = _derive_atom_id("mission-1", "source-1", "")
    id2 = _derive_atom_id("mission-1", "source-1", "")
    assert id1 == id2, "Empty content must still yield a stable atom_id"


def test_different_sources_give_different_ids():
    id1 = _derive_atom_id("mission-1", "source-A", "Same content text here")
    id2 = _derive_atom_id("mission-1", "source-B", "Same content text here")
    assert id1 != id2, "Different source_id must yield different atom_ids"


def test_uuid4_is_not_present_in_pipeline():
    """Regression guard: uuid4 must not appear in the pipeline atom_id derivation."""
    source = PIPELINE_PATH.read_text()
    assert "uuid.uuid4()" not in source, (
        "uuid.uuid4() found in pipeline.py — atom_id derivation is still non-deterministic"
    )


def test_uuid5_namespace_url_is_present_in_pipeline():
    """Positive guard: uuid5(NAMESPACE_URL, ...) must be present in pipeline.py."""
    source = PIPELINE_PATH.read_text()
    assert "uuid.uuid5(uuid.NAMESPACE_URL" in source, (
        "uuid.uuid5(uuid.NAMESPACE_URL not found in pipeline.py — deterministic fix was not applied"
    )
```

No mocking of the database is needed; the tests exercise the pure Python id-derivation logic directly.
  </action>
  <verify>
    <automated>cd /home/bamn/Sheppard && python -m pytest tests/test_atom_dedup.py -v 2>&1 | tail -20</automated>
  </verify>
  <done>
    All 6 tests in tests/test_atom_dedup.py pass (PASSED beside each test name, 6 passed in summary). No uuid4 reference remains in pipeline.py per test_uuid4_is_not_present_in_pipeline.
  </done>
</task>

</tasks>

<verification>
After both tasks complete, run:

    cd /home/bamn/Sheppard && python -m pytest tests/test_atom_dedup.py -v

Expected output: 6 passed.

Also confirm the change in place:

    grep -n "uuid" /home/bamn/Sheppard/src/research/condensation/pipeline.py

Expected: line 56 shows `import uuid`, line 89 shows `uuid.uuid5(uuid.NAMESPACE_URL`. No `uuid4` on line 89.
</verification>

<success_criteria>
- `grep "uuid.uuid4()" src/research/condensation/pipeline.py` returns no matches
- `grep "uuid.uuid5(uuid.NAMESPACE_URL" src/research/condensation/pipeline.py` returns line 89
- `python -m pytest tests/test_atom_dedup.py -v` exits 0 with 6 passed
- Re-running distillation on the same source will hit ON CONFLICT and update rather than insert a new row
</success_criteria>

<output>
After completion, create `.planning/gauntlet_phases/phase05a_dedup/SUMMARY.md` describing:
- What changed (pipeline.py line 89)
- Why (gap A11: uuid4 prevented ON CONFLICT from firing)
- Evidence (pytest output, grep confirmation)
- Verification decision: PASS or FAIL
</output>
