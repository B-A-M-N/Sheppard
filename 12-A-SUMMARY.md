# 12-A Summary

## Scope

Phase 12-A introduced deterministic, non-LLM derived claims on the `EvidencePacket`.

## Completed

- Added the derived claim engine in `src/research/derivation/engine.py`
- Exported the derivation module in `src/research/derivation/__init__.py`
- Integrated derived claims into `EvidencePacket` assembly in `src/research/reasoning/assembler.py`
- Extended `src/retrieval/validator.py` so multi-citation derived claims can be recomputed and verified
- Added dedicated validator coverage in `tests/retrieval/test_validator_derived.py`
- Existing derivation engine tests remain in `tests/research/derivation/test_engine.py`

## Behavioral Contract

- Derived claims remain ephemeral and are not persisted
- Supported derived checks:
  - delta
  - percent change
- Multi-citation grounding is validated against the combined cited evidence surface
- Single-citation validation behavior remains intact

## Open Follow-Up

- Add broader retrieval coverage for `retrieve_many()`
- Verify active-path model routing and contradiction flow before broader refactors
- Group and commit the remaining working-tree changes that are outside the 12-A/12-B validator scope

## Validation

Run:

```bash
python -m pytest tests/research/derivation/test_engine.py -v
python -m pytest tests/retrieval/test_validator_derived.py -v
```
