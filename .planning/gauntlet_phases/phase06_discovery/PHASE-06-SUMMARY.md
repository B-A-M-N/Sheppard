# Phase 06 Plan 01: Discovery Engine Audit Summary

**One-liner:** Static audit of Sheppard V3 discovery layer producing five evidence-grounded documents classifying each claimed capability as PARTIAL, OPEN, or VERIFIED PASS based on frontier.py, crawler.py, system.py, and domain_schema.py line references.

**Date completed:** 2026-03-28
**Phase:** 06-discovery
**Plan:** 01
**Type:** audit (no code changes)

---

## Files Produced

| File | Purpose |
|------|---------|
| `DISCOVERY_AUDIT.md` | Top-level 7-area classification table, per-area evidence, hard-fail assessment, overall verdict |
| `TAXONOMY_GENERATION_AUDIT.md` | Deep dive: parent_node_id gap, node count analysis, fallback nodes, classification |
| `SEARCH_BEHAVIOR_REPORT.md` | Break-on-first-success inversion, behavior table, engine inventory, SearXNG architecture |
| `URL_SELECTION_HEURISTICS.md` | Routing logic, whitelist classification vs. filtering, academic_only inactive state |
| `PHASE-06-VERIFICATION.md` | Checklist, evidence index, runtime-only items, missing/inflated claims, overall verdict |

---

## Classification Table (from DISCOVERY_AUDIT.md)

| Area | Claim | Classification | Root Cause |
|------|-------|----------------|------------|
| Taxonomic decomposition | LLM-driven 15-node topic taxonomy | PARTIAL | Node count not enforced; parent_node_id never populated at runtime |
| Search depth / deep mining | Deep mines up to page 5 | PARTIAL / MISCHARACTERIZED | Break-on-first-success — pages 2-5 are dedup fallback, not depth exploration |
| URL quality controls | Academic whitelist filters irrelevant URLs | PARTIAL | Whitelist classifies but does not filter; academic_only mode inactive at construction |
| Epistemic modes | 4-mode cycling per node | PARTIAL | exhausted_modes hardcoded set() on resume; no DB column to persist mode history |
| Obscure source discovery | Accesses specialized academic sources | PARTIAL | 5 general-purpose SearXNG engines only; no specialized API; policy not used for engine selection |
| Queue / backpressure | Non-blocking architecture | OPEN | rpush unbounded; frontier can outrun 8 vampires with no circuit-breaker |
| Visited URL persistence | URLs deduplicated across restarts | VERIFIED PASS | Phase 05B resolved; get_visited_urls correctly wired in _load_checkpoint |

---

## Overall Verdict

**PASS with five PARTIAL findings and one OPEN operational gap.**

No area is a clean FAIL: the structures, prompts, and logic exist in every case. No area is a clean PASS: enforcement is absent or incomplete in the runtime path for every claimed capability. This is the expected and correct outcome for a well-architected system where schema design and prompt engineering are ahead of runtime enforcement.

The queue/backpressure gap (OPEN) is the highest operational risk because it is unbounded by design — `rpush` with no depth limit and no circuit-breaker — rather than an oversight in an otherwise enforced system.

---

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1 | 7d43ac9 | DISCOVERY_AUDIT.md, TAXONOMY_GENERATION_AUDIT.md |
| Task 2 | b826892 | SEARCH_BEHAVIOR_REPORT.md, URL_SELECTION_HEURISTICS.md |
| Task 3 | b87b642 | PHASE-06-VERIFICATION.md |

---

## Deviations from Plan

None — plan executed exactly as written. All 5 deliverable files created with required content. No code changes were made (audit-only phase).

---

## Self-Check: PASSED

All 5 audit files confirmed present:
- DISCOVERY_AUDIT.md: exists, contains 8 PARTIAL occurrences, PASS verdict
- TAXONOMY_GENERATION_AUDIT.md: exists, contains parent_node_id (8 occurrences), frontier.py line 157 reference
- SEARCH_BEHAVIOR_REPORT.md: exists, contains break condition explanation, google,bing engine list
- URL_SELECTION_HEURISTICS.md: exists, contains academic_only (9 occurrences), system.py line references
- PHASE-06-VERIFICATION.md: exists, Runtime-Only section, PASS verdict, exhausted_modes references
