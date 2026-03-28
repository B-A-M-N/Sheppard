---
phase: 05a-dedup
plan: 01
subsystem: condensation-pipeline
tags: [dedup, determinism, uuid, gap-closure, A11]
requirements: [A11]
gap_closure: true
dependency_graph:
  requires: []
  provides: [deterministic-atom-id]
  affects: [store_atom_with_evidence, ON_CONFLICT_path]
tech_stack:
  added: []
  patterns: [uuid5-content-hash, idempotent-upsert]
key_files:
  modified:
    - src/research/condensation/pipeline.py
  created:
    - tests/test_atom_dedup.py
decisions:
  - "Use uuid5(NAMESPACE_URL, mission:source:content[:200]) as the atom_id derivation key — mission and source scoping prevents cross-mission collisions while content[:200] keeps the namespace string bounded"
metrics:
  duration_minutes: 5
  tasks_completed: 2
  files_changed: 2
  completed_date: "2026-03-27"
---

# Phase 05a Plan 01: Deterministic atom_id (gap A11) Summary

**One-liner:** Replaced uuid4 with uuid5(NAMESPACE_URL, mission:source:content[:200]) in pipeline.py line 89 so the ON CONFLICT (atom_id) upsert path fires on re-run instead of inserting duplicates.

---

## What Changed

### pipeline.py line 89

**Before:**
```python
atom_id = str(uuid.uuid4())
```

**After:**
```python
atom_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{source_id}:{atom_dict.get('content', '')[:200]}"))
```

No other lines were modified. The `import uuid` at line 56 already covers both `uuid4` and `uuid5` — no import change was needed. The atom_id column type remains UUID; the only change is derivation strategy.

---

## Why

Gap A11: every pipeline run called `uuid.uuid4()` for each atom, generating a fresh random UUID regardless of whether the atom content was identical to a previous run. The `store_atom_with_evidence` function in `src/memory/storage_adapter.py` uses `ON CONFLICT (atom_id) DO UPDATE` — this upsert can only fire when the incoming atom_id matches an existing row. With uuid4, that match was statistically impossible, so every re-run of distillation on already-processed sources inserted new duplicate rows into `knowledge.knowledge_atoms`.

The fix derives atom_id from a deterministic namespace string combining:
- `mission_id` — prevents cross-mission atom collisions
- `source_id` — prevents same-content-from-different-source aliasing
- `content[:200]` — the distinguishing content prefix (bounded to keep the namespace string practical)

With uuid5, the same (mission, source, content) triple always resolves to the same UUID, so the ON CONFLICT path fires and updates the existing row instead of inserting a duplicate.

---

## Evidence

### grep confirmation

```
$ grep -n "uuid.uuid5(uuid.NAMESPACE_URL" src/research/condensation/pipeline.py
89:                        atom_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{source_id}:{atom_dict.get('content', '')[:200]}"))

$ grep -n "uuid.uuid4()" src/research/condensation/pipeline.py
(no output — uuid4 is absent)
```

### pytest output (all 6 passed)

```
============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-9.0.2, pluggy-1.6.0
collecting ... collected 6 items

tests/test_atom_dedup.py::test_atom_id_is_deterministic PASSED           [ 16%]
tests/test_atom_dedup.py::test_different_content_gives_different_id PASSED [ 33%]
tests/test_atom_dedup.py::test_empty_content_is_stable PASSED            [ 50%]
tests/test_atom_dedup.py::test_different_sources_give_different_ids PASSED [ 66%]
tests/test_atom_dedup.py::test_uuid4_is_not_present_in_pipeline PASSED   [ 83%]
tests/test_atom_dedup.py::test_uuid5_namespace_url_is_present_in_pipeline PASSED [100%]

======================== 6 passed, 2 warnings in 0.80s =========================
```

Warnings are pre-existing Pydantic v1-style config in `src/llm/models.py` — unrelated to this change, out of scope.

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Verification Decision: PASS

All success criteria met:
- `grep "uuid.uuid4()" src/research/condensation/pipeline.py` returns no matches
- `grep "uuid.uuid5(uuid.NAMESPACE_URL" src/research/condensation/pipeline.py` returns line 89
- `python -m pytest tests/test_atom_dedup.py -v` exits 0 with 6 passed
- Re-running distillation on the same source will now hit ON CONFLICT and update rather than insert a new row

---

## Commits

| Task | Commit  | Message |
|------|---------|---------|
| 1    | 224cd03 | feat(05a-01): replace uuid4 with deterministic uuid5 in pipeline.py |
| 2    | 3014319 | test(05a-01): add deterministic atom_id verification suite |

## Self-Check: PASSED

- `/home/bamn/Sheppard/src/research/condensation/pipeline.py` modified — uuid5 on line 89 confirmed
- `/home/bamn/Sheppard/tests/test_atom_dedup.py` created — 6 tests, all pass
- Commit 224cd03 exists
- Commit 3014319 exists
