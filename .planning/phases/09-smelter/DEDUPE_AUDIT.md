# Phase 09 Audit: Deduplication

**Date:** 2026-03-29

---

## Deduplication Mechanism

- **Atom ID generation** (`src/research/condensation/pipeline.py`, line 88):
  ```python
  atom_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{mission_id}:{source_id}:{atom_dict.get('content', '')[:200]}"))
  ```
- Deterministic **within a source**: Same content within the same source produces same atom_id (content truncated to 200 chars as the hash input).
- Deterministic **across runs** of the same source: Yes, given same `mission_id`, `source_id`, and content prefix.

---

## Cross-Source Deduplication

- **Not implemented.** The method `consolidate_atoms` (pipeline.py lines 154-156) is a stub: "Implementation pending V3 migration..."
- No global content-based deduplication exists. Identical atoms from different sources will receive different `atom_id` values because `source_id` differs.

---

## Determinism Assessment

| Scenario | Deterministic? | Reason |
|----------|----------------|--------|
| Same source, same content, same mission | Yes | UUID5 over consistent inputs |
| Different sources, same content | No | Different `source_id` yields different namespace/hash |
| Same source, content with >200 char prefix same | Yes | Only first 200 chars used; longer content beyond 200 not considered |
| Same source, content differs after 200 chars | Potentially same | Only first 200 chars matter; collisions possible if two distinct documents share first 200 chars |

**Conclusion:** Determinism is **local to source**, not global. The requirement "deduplication deterministic" is **PARTIALLY MET** — per-source determinism exists, but global dedupe scope is absent.

---

## Edge Cases

- **Near-duplicate content with different prefixes:** Could produce different atom_ids if first 200 chars differ, even if remainder is identical. This is not true deduplication but rather exact-prefix dedupe.
- **Race conditions:** Not applicable; processing sequential (semaphore limit 2) per pipeline.
- **Source re-processing:** If a source is re-fetched and re-smelted, same atoms will reproduce same atom_id (idempotent) if `mission_id` and `source_id` unchanged.

---

## Risk

Without global deduplication, the knowledge atom layer may accumulate redundant atoms across sources, increasing storage负担 and requiring later consolidation. This is noted as pending work and should be clarified as either out-of-scope for Phase 09 or a gap to close.

**Status:** `PARTIAL` — meets a minimal interpretation (per-source dedupe) but not a stronger global interpretation.
