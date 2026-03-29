---
phase: 06-discovery
verified: 2026-03-28T00:00:00Z
status: passed
score: 5/5 must-haves verified
---

# Phase 06: Discovery Engine Audit — Verification Result

**Phase Goal:** Produce five audit documents that record a claim-vs-behavior alignment audit of the Sheppard V3 discovery engine. Establish an evidence-grounded record of what the discovery layer actually does versus what it claims to do, with every finding traceable to a specific file and line number.

**Verified:** 2026-03-28
**Status:** PASSED
**Re-verification:** No — initial verification

---

## What Was Checked

1. All 5 required artifact files exist at the declared paths.
2. Each file contains the required content string specified in PLAN.md must_haves.
3. Line-number evidence is present and dense throughout each document.
4. PHASE-06-VERIFICATION.md carries an explicit overall verdict, a runtime-only items table, and a missing/inflated claims section.

---

## Artifact Results

### 1. DISCOVERY_AUDIT.md

**Required content:** contains `"PARTIAL"`
**Result:** PASS — `"PARTIAL"` appears 8 times.

**Content check:**
- 7-row classification table present with all required areas: Taxonomic decomposition, Search depth, URL quality controls, Epistemic modes, Obscure source discovery, Queue/backpressure, Visited URL persistence.
- All required classifications present (PARTIAL, PARTIAL/MISCHARACTERIZED, OPEN, VERIFIED PASS).
- Per-area evidence summaries present for all 7 areas.
- Hard-fail assessment table present (4 conditions, all CLEARED).
- Overall verdict present: `**Verdict: PASS with multiple PARTIAL findings**`

**Line-number evidence spot-check:** Dense throughout. Sample findings with explicit line citations in every per-area summary section. Example: `frontier.py line 203 prompts for exactly 15 nodes`, `Lines 157-171 (_save_node) construct MissionNode without setting parent_node_id`, `crawler.py lines 294-330`, `redis.py (lines 83-84)`.

**Status: VERIFIED**

---

### 2. TAXONOMY_GENERATION_AUDIT.md

**Required content:** contains `"parent_node_id"`
**Result:** PASS — `"parent_node_id"` appears 8 times.

**Content check:**
- Decomposition prompt analysis covers `_frame_research_policy` (frontier.py lines 200-215), the 15-node hardcoded target, extraction loop (lines 251-263), node cleaning with `re.sub`, and 3-character minimum.
- Node count analysis section present: prompt requests 15, extraction enforces 0 minimum, fallback provides 5.
- `parent_node_id` gap documented as the central finding of the document, with:
  - `domain_schema.py` line 107 (`parent_node_id: Optional[str] = None`) cited
  - `_save_node` (frontier.py lines 157-171) documented as omitting `parent_node_id`
  - `_respawn_nodes` (frontier.py lines 329-352) documented as discarding the parent-child relationship at DB write
  - Code block for `_save_node` construction quoted verbatim
- Fallback behavior documented with 5 named fallback nodes listed.
- Classification: `**PARTIAL**`
- "What Would Constitute PASS" section with 2 bullet points.

**Status: VERIFIED**

---

### 3. SEARCH_BEHAVIOR_REPORT.md

**Required content:** contains `"break"`
**Result:** PASS — `"break"` appears 7 times.

**Content check:**
- Central inversion documented: the break condition at lines 322-326 (`if page_new_count > 0: break`) fires as soon as any page yields a URL not in `visited_urls`.
- Fresh mission behavior explicitly stated: page 2 is never fetched when `visited_urls` is empty.
- Pages 2-5 identified as dedup fallback, not depth exploration — phrasing matches the required truth.
- Behavior table present with 3 rows (Fresh, Near-saturation, Fully saturated).
- SearXNG architecture section present with 3 hardcoded instance URLs, `asyncio.as_completed` race documented.
- `pageno` forwarding confirmed with quoted payload block showing `"engines": "google,bing,brave,duckduckgo,qwant"`.
- Engine inventory table present with 5 in-payload entries and 4 absent academic engines.
- ResearchPolicy not used in engine selection documented.
- Classification: `**PARTIAL / MISCHARACTERIZED**`

**Status: VERIFIED**

---

### 4. URL_SELECTION_HEURISTICS.md

**Required content:** contains `"academic_only"`
**Result:** PASS — `"academic_only"` appears 9 times.

**Content check:**
- `ACADEMIC_WHITELIST_DOMAINS` constant quoted verbatim from crawler.py lines 25-30 (13 entries).
- `_is_academic` implementation documented as informational only — does not gate or reject URLs.
- `_route_url` documented as lane assignment (fast/slow), not rejection — distinction `classification != filtering` explicitly stated.
- `academic_only` mode documented as wired but inactive:
  - Implementation cited at crawler.py line 185
  - Default `False` at line 71 cited
  - `FirecrawlLocalClient` construction in system.py lines 125-128 quoted verbatim showing `academic_only` argument absent
  - Result stated: `academic_only` flag is dead code in the system construction path
- `discover_and_enqueue` quality gate section confirms no `_is_academic` call before `enqueue_job`.
- Queue/backpressure note cross-references DISCOVERY_AUDIT.md.
- Classification: `**PARTIAL**`
- "What Would Constitute PASS" with 2 bullet points.

**Status: VERIFIED**

---

### 5. PHASE-06-VERIFICATION.md

**Required content:** contains `"PARTIAL"`
**Result:** PASS — `"PARTIAL"` appears 11 times.

**Required structure checks:**

| Check | Result | Evidence |
|-------|--------|---------|
| Explicit overall verdict | PASS | Line 68: `Phase 06 verdict: **PASS with five PARTIAL findings and one OPEN operational gap.**` |
| Verdict in `## Verdict` section | PASS | Lines 58-68 form the Verdict section with `**Status: PASS**` |
| Runtime-only items section | PASS | `## Runtime-Only Items` at line 32 with 5-row table |
| Missing/Inflated claims section | PASS | `## Missing / Inflated Claims` at line 46 with 5 numbered entries |
| Discovery claims checklist with [x]/[ ] markers | PASS | 5 checklist items with `[x]` markers and per-item PARTIAL/PASS classification |
| Evidence index table | PASS | 7-row table mapping each claim to its audit document |
| `exhausted_modes` documented | PASS | Lines 9 and 54 cite `exhausted_modes=set()` on restart |

**Runtime-only items (5 entries):** SearXNG engine config, SearXNG instance availability, Firecrawl-local performance, Actual LLM node quality, Queue depth under load — all correctly identified as out of scope for static analysis.

**Missing/Inflated claims (5 entries):**
1. "Deep mine up to page 5" — break fires on page 1 in fresh missions
2. "Topic taxonomy" — `parent_node_id` never set, graph flat
3. "Academic URL filtering" — classifies but does not filter; `academic_only` inactive
4. "4-mode epistemic cycling" — `exhausted_modes=set()` discards state on restart
5. "Non-blocking architecture" (implicit) — unbounded `rpush`, no backpressure

**Status: VERIFIED**

---

## Observable Truths Assessment

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Every discovery claim is classified as PASS, PARTIAL, or FAIL with line-number evidence | VERIFIED | DISCOVERY_AUDIT.md classification table + per-area summaries; PHASE-06-VERIFICATION.md checklist — all 7 areas have classifications with specific file:line cites |
| 2 | TAXONOMY_GENERATION_AUDIT.md documents the parent_node_id gap with specific file locations | VERIFIED | Central finding section documents `domain_schema.py` line 107, `frontier.py` lines 157-171 (`_save_node`), lines 329-352 (`_respawn_nodes`); code block quoted; result stated: every node has `parent_node_id = None` |
| 3 | SEARCH_BEHAVIOR_REPORT.md explains why pages 2-5 are dedup fallback, not depth exploration | VERIFIED | Break condition at lines 322-326 quoted and explained; fresh mission behavior (page 2 never reached) explicitly stated; behavior table maps all 3 mission states |
| 4 | URL_SELECTION_HEURISTICS.md documents that academic_only is wired but inactive at construction | VERIFIED | Implementation at crawler.py line 185 cited; default `False` at line 71; system.py lines 125-128 construction quoted showing absent argument; conclusion: dead code in system construction path |
| 5 | PHASE-06-VERIFICATION.md carries an explicit overall verdict and lists runtime-only items separately | VERIFIED | Verdict section at line 58-68 with `PASS with five PARTIAL findings and one OPEN operational gap`; `## Runtime-Only Items` section at line 32; `## Missing / Inflated Claims` at line 46 |

**Score: 5/5 truths verified**

---

## Anti-Patterns Scan

Scanned all 5 audit documents for: TODO/FIXME markers, placeholder language, empty sections, claims without evidence.

- No TODO, FIXME, or placeholder language found in any document.
- No sections present without supporting evidence.
- All classification labels (PARTIAL, OPEN, VERIFIED PASS) are backed by file:line citations.
- No inflation or softening of findings detected: the break-on-first-success inversion, the `parent_node_id` flat-graph result, and the `academic_only` dead-code conclusion are all stated directly.

**Anti-patterns: None found.**

---

## Overall Assessment

All five audit documents exist, contain the required content strings, and are substantive — they are evidence-grounded analyses, not placeholders. Every document contains dense file:line citations traceable to the actual source code. The five observable truths derived from the phase goal are all satisfied.

PHASE-06-VERIFICATION.md fulfills all structural requirements: explicit overall verdict, runtime-only items table (5 entries), missing/inflated claims list (5 entries), and a checklist covering all five claimed discovery capabilities.

**Phase 06 goal: ACHIEVED.**

The discovery layer audit produces the expected outcome described in the plan objective: `PASS with multiple PARTIAL findings`. This is the correct and healthy result — the structures exist, enforcement is incomplete in several runtime paths.

---

_Verified: 2026-03-28_
_Verifier: Claude (gsd-verifier)_
