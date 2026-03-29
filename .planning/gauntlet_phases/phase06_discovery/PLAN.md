---
phase: 06-discovery
plan: 01
type: audit
wave: 1
depends_on: []
files_modified: []
autonomous: true
requirements: [DISCOVERY-01, DISCOVERY-02, DISCOVERY-03, DISCOVERY-04, DISCOVERY-05]

must_haves:
  truths:
    - "Every discovery claim is classified as PASS, PARTIAL, or FAIL with line-number evidence"
    - "TAXONOMY_GENERATION_AUDIT.md documents the parent_node_id gap with specific file locations"
    - "SEARCH_BEHAVIOR_REPORT.md explains why pages 2-5 are dedup fallback, not depth exploration"
    - "URL_SELECTION_HEURISTICS.md documents that academic_only is wired but inactive at construction"
    - "PHASE-06-VERIFICATION.md carries an explicit overall verdict and lists runtime-only items separately"
  artifacts:
    - path: ".planning/gauntlet_phases/phase06_discovery/DISCOVERY_AUDIT.md"
      provides: "Top-level audit with per-area classification table and verdict"
      contains: "PARTIAL"
    - path: ".planning/gauntlet_phases/phase06_discovery/TAXONOMY_GENERATION_AUDIT.md"
      provides: "Deep dive on decomposition, parent_node_id gap, fallback nodes"
      contains: "parent_node_id"
    - path: ".planning/gauntlet_phases/phase06_discovery/SEARCH_BEHAVIOR_REPORT.md"
      provides: "Search depth inversion finding, break condition, engine inventory"
      contains: "break"
    - path: ".planning/gauntlet_phases/phase06_discovery/URL_SELECTION_HEURISTICS.md"
      provides: "Routing logic, whitelist classification, academic_only inactive state"
      contains: "academic_only"
    - path: ".planning/gauntlet_phases/phase06_discovery/PHASE-06-VERIFICATION.md"
      provides: "Verification checklist, runtime-only items, overall verdict"
      contains: "PARTIAL"
  key_links:
    - from: "DISCOVERY_AUDIT.md"
      to: "PHASE-06-VERIFICATION.md"
      via: "classification table drives checklist status"
    - from: "TAXONOMY_GENERATION_AUDIT.md"
      to: "DISCOVERY_AUDIT.md"
      via: "supplies Area 1 row evidence"
    - from: "SEARCH_BEHAVIOR_REPORT.md"
      to: "DISCOVERY_AUDIT.md"
      via: "supplies Area 2 row evidence"
    - from: "URL_SELECTION_HEURISTICS.md"
      to: "DISCOVERY_AUDIT.md"
      via: "supplies Area 3 row evidence"
---

<objective>
Produce five audit documents that record a claim-vs-behavior alignment audit of the Sheppard V3 discovery engine.

Purpose: Establish an evidence-grounded record of what the discovery layer actually does versus what it claims to do, with every finding traceable to a specific file and line number. No code changes are made.

Output: DISCOVERY_AUDIT.md, TAXONOMY_GENERATION_AUDIT.md, SEARCH_BEHAVIOR_REPORT.md, URL_SELECTION_HEURISTICS.md, PHASE-06-VERIFICATION.md written to `.planning/gauntlet_phases/phase06_discovery/`.

Expected result: PASS with multiple PARTIAL findings. That is the correct and healthy outcome — the structures exist, enforcement is absent or incomplete in several areas. A clean PASS across all areas is not expected and would indicate an insufficiently rigorous audit.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/gauntlet_phases/phase06_discovery/RESEARCH.md
@.planning/gauntlet_phases/phase06_discovery/PHASE-06-PLAN.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write DISCOVERY_AUDIT.md and TAXONOMY_GENERATION_AUDIT.md</name>

  <read_first>
    Primary sources (read before writing):
    - /home/bamn/Sheppard/src/research/acquisition/frontier.py
      Lines 26-37   — EpistemicMode enum definitions
      Lines 157-171 — _save_node (no parent_node_id set)
      Lines 200-215 — _frame_research_policy decomposition prompt (15 nodes)
      Lines 251-263 — node extraction loop with cleaning
      Lines 266-277 — fallback nodes (5 hardcoded)
      Lines 286-291 — mode selection loop
      Lines 294-310 — mode injection into query prompt
      Lines 329-352 — _respawn_nodes (no parent_node_id in child save)
      Lines 141-155 — _load_checkpoint (exhausted_modes=set())
    - /home/bamn/Sheppard/src/research/domain_schema.py
      Line 107       — MissionNode.parent_node_id field declaration
      Lines 104-128  — full MissionNode schema (no exhausted_modes field)
  </read_first>

  <action>
    Write TWO files.

    --- FILE 1: .planning/gauntlet_phases/phase06_discovery/DISCOVERY_AUDIT.md ---

    Structure:

    # Phase 06: Discovery Engine Audit

    ## Audit Method
    One paragraph: static code inspection only; all findings cite file + line; no runtime execution; visited URL persistence treated as resolved input (Phase 05B).

    ## Classification Table
    A markdown table with columns: Area | Claim | Classification | Root Cause
    Rows (use these exact classifications — do not deviate):

    | Area | Claim | Classification | Root Cause |
    |------|-------|----------------|------------|
    | Taxonomic decomposition | LLM-driven 15-node topic taxonomy | PARTIAL | Node count not enforced; parent_node_id never populated at runtime |
    | Search depth / deep mining | Deep mines up to page 5 | PARTIAL / MISCHARACTERIZED | Break-on-first-success — pages 2-5 are dedup fallback, not depth exploration |
    | URL quality controls | Academic whitelist filters irrelevant URLs | PARTIAL | Whitelist classifies but does not filter; academic_only mode inactive at construction |
    | Epistemic modes | 4-mode cycling per node | PARTIAL | exhausted_modes hardcoded set() on resume; no DB column to persist mode history |
    | Obscure source discovery | Accesses specialized academic sources | PARTIAL | 5 general-purpose SearXNG engines only; no specialized API; policy not used for engine selection |
    | Queue / backpressure | Non-blocking architecture | OPEN | rpush unbounded; frontier can outrun 8 vampires with no circuit-breaker |
    | Visited URL persistence | URLs deduplicated across restarts | VERIFIED PASS | Phase 05B resolved; get_visited_urls correctly wired in _load_checkpoint |

    ## Per-Area Evidence Summaries
    For each area in the table, write a brief subsection (2-4 sentences) citing specific file:line evidence. Use the findings from RESEARCH.md verbatim where available. Do not paraphrase the evidence — cite it precisely.

    Example for Taxonomic decomposition:
    > frontier.py line 203 prompts for exactly 15 nodes, but lines 251-263 iterate data.get('nodes', []) with no minimum count enforcement. Lines 157-171 (_save_node) construct MissionNode without setting parent_node_id, which defaults to None for every node written. Lines 329-352 (_respawn_nodes) also call _save_node without passing parent_node_id. The hierarchy declared in domain_schema.py line 107 is never populated at runtime.

    Continue this pattern for all 7 areas.

    ## Hard-Fail Assessment
    A table mapping the 4 hard-fail conditions from the phase spec to their risk level and disposition (CLEARED or OPEN), drawing from the RESEARCH.md hard-fail risk assessment section.

    ## Overall Verdict
    Single line: **Verdict: PASS with multiple PARTIAL findings**
    One paragraph explaining: no area is a clean FAIL (structures exist), no area is a clean PASS (enforcement absent or incomplete). Queue/backpressure is the highest operational risk because it is unbounded by design.

    ---

    --- FILE 2: .planning/gauntlet_phases/phase06_discovery/TAXONOMY_GENERATION_AUDIT.md ---

    Structure:

    # Taxonomy Generation Audit

    ## Claim Under Review
    One sentence stating the claim: discovery is driven by structured, LLM-generated research nodes representing a topic taxonomy, not flat keyword search.

    ## Decomposition Prompt Analysis
    Subsection covering:
    - What _frame_research_policy (frontier.py lines 200-215) actually asks the LLM for
    - The exact target count (15 nodes) and that it is hardcoded as numbered labels in the prompt
    - That the extraction loop (lines 251-263) iterates data.get('nodes', []) with no minimum count enforcement
    - Node string cleaning with re.sub (lines 253-258), 3-character minimum
    - The 5 hardcoded fallback nodes (lines 266-277) with their exact names as they appear in code

    ## Node Count Analysis
    Subsection: prompt requests 15, extraction enforces 0 minimum, fallback provides 5. Node count is LLM-dependent. Include exact line numbers.

    ## parent_node_id Gap
    Subsection — this is the central finding for this document:
    - MissionNode declares parent_node_id: Optional[str] = None (domain_schema.py line 107)
    - _save_node (frontier.py lines 157-171) constructs MissionNode without setting parent_node_id
    - _respawn_nodes (frontier.py lines 329-352) spawns child nodes but also calls _save_node without parent_node_id
    - Result: every node written to the database has parent_node_id = None; the graph is structurally flat at runtime
    - Quote the relevant _save_node construction code block

    ## Fallback Behavior
    When LLM generation fails or JSON parse fails: exactly 5 hardcoded fallback nodes are used. List them. State that the fallback is a safe degradation but that missions running on fallback nodes have lower topic specificity.

    ## Classification
    PARTIAL — structure present in schema and prompt, enforcement absent in runtime path.

    ## What Would Constitute PASS
    Two bullet points: (1) parent_node_id populated in _save_node and _respawn_nodes; (2) node count >= some minimum enforced after LLM extraction.
  </action>

  <verify>
    <automated>
      grep -c "PARTIAL" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/DISCOVERY_AUDIT.md
      grep "parent_node_id" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/TAXONOMY_GENERATION_AUDIT.md
      grep "PARTIAL" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/TAXONOMY_GENERATION_AUDIT.md
    </automated>
  </verify>

  <done>
    DISCOVERY_AUDIT.md exists and contains a classification table with all 7 areas, an overall verdict of PASS with PARTIAL findings, and per-area evidence citing file:line references.
    TAXONOMY_GENERATION_AUDIT.md exists and contains the parent_node_id gap as the central finding, with frontier.py and domain_schema.py line references, and a PARTIAL classification.
  </done>
</task>

<task type="auto">
  <name>Task 2: Write SEARCH_BEHAVIOR_REPORT.md and URL_SELECTION_HEURISTICS.md</name>

  <read_first>
    Primary sources (read before writing):
    - /home/bamn/Sheppard/src/research/acquisition/crawler.py
      Lines 25-30    — ACADEMIC_WHITELIST_DOMAINS definition
      Lines 47-51    — SearXNG instance pool (3 hardcoded URLs)
      Lines 71       — academic_only default False
      Lines 112-132  — _route_url (lane decision only, no rejection)
      Lines 185      — academic_only flag in crawl_topic
      Lines 245-278  — _search method, pageno forwarding, first-success-wins race
      Lines 255-258  — SearXNG engines payload parameter
      Lines 265-278  — asyncio.as_completed race, remaining tasks cancelled
      Lines 294-330  — discover_and_enqueue page loop
      Lines 322-326  — break condition (page_new_count > 0)
      Lines 385-387  — _is_academic(url) implementation
    - /home/bamn/Sheppard/src/core/system.py
      Lines 125-128  — FirecrawlLocalClient construction (academic_only default)
    - /home/bamn/Sheppard/src/memory/adapters/redis.py
      Lines 83-84    — enqueue_job rpush with no size check
  </read_first>

  <action>
    Write TWO files.

    --- FILE 1: .planning/gauntlet_phases/phase06_discovery/SEARCH_BEHAVIOR_REPORT.md ---

    Structure:

    # Search Behavior Report

    ## Claim Under Review
    Discovery deep mines up to page 5 to find new URLs, providing genuine search depth beyond page 1.

    ## Page Loop Analysis — The Central Inversion
    This is the central finding. Write it clearly and precisely.

    Subsection explaining:
    - The loop in discover_and_enqueue (crawler.py lines 294-330) iterates for page in range(1, 6)
    - The break condition (lines 322-326): if page_new_count > 0: break
    - What this actually means: the loop stops as soon as any page yields at least one URL not in visited_urls
    - In a fresh mission (empty visited_urls), every URL on page 1 is new, so page_new_count > 0 on page 1, and the loop always breaks after page 1
    - Pages 2-5 are only reached when pages 1 through N-1 are entirely exhausted duplicates
    - This is dedup fallback behavior, not depth exploration
    - Quote the break condition code block exactly as it appears

    Include a behavior table:
    | Mission State | Pages Actually Fetched | Reason |
    |---------------|------------------------|--------|
    | Fresh (visited_urls empty) | 1 | Every URL on page 1 is new; break fires immediately |
    | Near-saturation (many known URLs) | 2-5 | Pages 1..N are all duplicates; loop continues until a new URL is found |
    | Fully saturated | 1 (empty result) | _search returns nothing; inner break fires on line 300 |

    ## SearXNG Architecture
    Subsection covering:
    - Three hardcoded SearXNG instance URLs (crawler.py lines 47-51)
    - asyncio.as_completed race: first successful response used, remaining cancelled (lines 265-278)
    - pageno parameter correctly forwarded to SearXNG (lines 255-257)
    - The five general-purpose engines in the payload: google, bing, brave, duckduckgo, qwant (lines 255-257)
    - No academic-specific engines (Semantic Scholar API, PubMed, CORE, BASE, CrossRef) called directly

    ## Engine Inventory
    A table:
    | Engine | Type | In SearXNG Payload |
    |--------|------|--------------------|
    | google | General web | Yes |
    | bing | General web | Yes |
    | brave | General web | Yes |
    | duckduckgo | General web | Yes |
    | qwant | General web | Yes |
    | Semantic Scholar API | Academic | No — not in payload |
    | PubMed / NCBI | Academic | No — not in payload |
    | CORE | Academic open access | No — not in payload |
    | CrossRef | Academic | No — not in payload |

    Note: Whether the SearXNG instances at the configured addresses have Google Scholar or similar scholarly engines enabled is a runtime-only question that cannot be determined from static analysis.

    ## ResearchPolicy — Not Used in Engine Selection
    Short subsection: _frame_research_policy sets self.policy with subject_class and authority_indicators fields. Neither field is passed to _search or included in the SearXNG payload. Policy guides query tone via the prompt but does not alter engine selection or domain targeting.

    ## Classification
    PARTIAL / MISCHARACTERIZED — the loop structure technically supports 5 pages, but the break-on-first-success semantics mean this is dedup fallback, not active depth exploration. The five-engine SearXNG integration is real; specialized academic API access is not implemented.

    ---

    --- FILE 2: .planning/gauntlet_phases/phase06_discovery/URL_SELECTION_HEURISTICS.md ---

    Structure:

    # URL Selection Heuristics Audit

    ## Claim Under Review
    URL quality is filtered using an academic whitelist; non-relevant URLs are rejected.

    ## ACADEMIC_WHITELIST_DOMAINS
    Subsection: quote the full constant definition from crawler.py lines 25-30. State the 13 entries. Then explain that _is_academic(url) (lines 385-387) checks whether any whitelist entry appears as a substring in the domain, and its return value is used only to set source_type = "academic" vs. "web" on CrawlResult. It does not gate or reject any URL.

    ## _route_url — Lane Assignment, Not Rejection
    Subsection: _route_url (crawler.py lines 112-132) returns "fast" or "slow". This is a processing-lane decision: "slow" routes PDFs and known static domains to Redis offload. _route_url never returns a value that causes a URL to be dropped or skipped. Include this distinction explicitly: classification != filtering.

    ## academic_only Mode — Wired but Inactive
    This is a key finding. Write clearly:
    - academic_only flag is declared in crawl_topic (crawler.py line 185): if self.academic_only is True, non-academic URLs are skipped
    - The default is False (crawler.py line 71)
    - FirecrawlLocalClient is constructed in system.py lines 125-128 WITHOUT setting academic_only=True
    - Therefore, academic_only mode is implemented in the crawler but never activated via the system construction path
    - Result: all URLs passing the visited_urls check are enqueued to queue:scraping regardless of academic classification

    ## discover_and_enqueue — No Quality Gate
    Subsection: in discover_and_enqueue (crawler.py lines 294-330), there is no call to _is_academic and no domain filtering before enqueue_job. Every URL not in visited_urls is enqueued unconditionally. Cite line range.

    ## Queue / Backpressure Note
    Short note: enqueue_job (redis.py lines 83-84) is an unbounded rpush with no llen check before push and no maximum queue depth configuration. This is an operational risk distinct from URL quality but related to discovery enqueue behavior. Cross-reference: this gap is classified as OPEN in DISCOVERY_AUDIT.md.

    ## Classification
    PARTIAL — ACADEMIC_WHITELIST_DOMAINS exists and correctly classifies URLs by source type. It does not filter or reject URLs. academic_only mode is implemented but disabled at the system construction site. URL quality controls are present as infrastructure but inactive in the runtime path.

    ## What Would Constitute PASS
    Two bullet points: (1) academic_only=True set during FirecrawlLocalClient construction for missions requiring academic filtering, or a per-mission flag wired through; (2) a pre-enqueue domain quality check in discover_and_enqueue that calls _is_academic or applies a reject list.
  </action>

  <verify>
    <automated>
      grep "break" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/SEARCH_BEHAVIOR_REPORT.md
      grep "academic_only" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/URL_SELECTION_HEURISTICS.md
      grep "PARTIAL" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/SEARCH_BEHAVIOR_REPORT.md
      grep "PARTIAL" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/URL_SELECTION_HEURISTICS.md
    </automated>
  </verify>

  <done>
    SEARCH_BEHAVIOR_REPORT.md exists and clearly explains the break-on-first-success inversion with the behavior table and engine inventory.
    URL_SELECTION_HEURISTICS.md exists and documents that academic_only is wired but inactive at construction, with system.py line references confirming the gap.
  </done>
</task>

<task type="auto">
  <name>Task 3: Write PHASE-06-VERIFICATION.md</name>

  <read_first>
    Reference files (scan before writing — these provide the checklist evidence):
    - /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/DISCOVERY_AUDIT.md  (written in Task 1)
    - /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/TAXONOMY_GENERATION_AUDIT.md  (written in Task 1)
    - /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/SEARCH_BEHAVIOR_REPORT.md  (written in Task 2)
    - /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/URL_SELECTION_HEURISTICS.md  (written in Task 2)
    Primary source confirmation:
    - /home/bamn/Sheppard/src/research/acquisition/frontier.py  lines 143-148 (exhausted_modes=set())
    - /home/bamn/Sheppard/src/memory/storage_adapter.py  lines 532-534 (get_visited_urls impl)
  </read_first>

  <action>
    Write ONE file: .planning/gauntlet_phases/phase06_discovery/PHASE-06-VERIFICATION.md

    Use the verification template from the phase spec as the structural skeleton, then populate it with evidence from the audit documents produced in Tasks 1 and 2.

    Structure:

    # Phase 06 Verification

    ## Discovery Claims Checklist

    Use this exact checklist format. Each item should be checked [x] or unchecked [ ] based on whether the claim is evidenced:

    - [x] Taxonomic decomposition implemented
      Evidence: _frame_research_policy prompts for 15 nodes (frontier.py lines 200-215); fallback to 5 hardcoded nodes on LLM failure (lines 266-277). Node count not enforced; parent_node_id never set at runtime. PARTIAL.
    - [x] Epistemic modes defined and used
      Evidence: Four modes defined (frontier.py lines 26-37); mode selection and injection implemented (lines 286-310); exhausted_modes reset to set() on every restart (line 147). PARTIAL — state loss on resume.
    - [x] Multi-page search structure present
      Evidence: Page loop range(1,6) in discover_and_enqueue (crawler.py lines 294-330). PARTIAL — break-on-first-success means pages 2-5 are dedup fallback. See SEARCH_BEHAVIOR_REPORT.md.
    - [x] Deduplication logic present
      Evidence: visited_urls check in discover_and_enqueue; get_visited_urls implemented and wired in _load_checkpoint (frontier.py line 150). VERIFIED PASS (Phase 05B).
    - [x] URL quality infrastructure exists
      Evidence: ACADEMIC_WHITELIST_DOMAINS (crawler.py lines 25-30); academic_only mode implemented (line 185). PARTIAL — whitelist classifies but does not filter; academic_only inactive at construction.

    ## Evidence Index

    A table pointing from each claim to its audit document:

    | Claim | Audit Document | Classification |
    |-------|---------------|----------------|
    | Taxonomic decomposition | TAXONOMY_GENERATION_AUDIT.md | PARTIAL |
    | Epistemic modes | DISCOVERY_AUDIT.md §Area 4 | PARTIAL |
    | Search depth / deep mining | SEARCH_BEHAVIOR_REPORT.md | PARTIAL / MISCHARACTERIZED |
    | URL quality controls | URL_SELECTION_HEURISTICS.md | PARTIAL |
    | Obscure source discovery | DISCOVERY_AUDIT.md §Area 5 | PARTIAL |
    | Queue / backpressure | DISCOVERY_AUDIT.md §Area 6 | OPEN |
    | Visited URL persistence | DISCOVERY_AUDIT.md §Area 7 | VERIFIED PASS |

    ## Runtime-Only Items

    A section explicitly listing items that could not be verified by static analysis and require a live run to confirm:

    | Item | Why Unverifiable Statically | Impact |
    |------|----------------------------|--------|
    | SearXNG engine config on instances | Configured in SearXNG admin UI, not in code | Determines whether scholarly engines (Google Scholar, Semantic Scholar, Unpaywall) are active |
    | SearXNG instance availability | Network-dependent | Affects whether any search results are returned |
    | Firecrawl-local performance | Depends on running service | Determines effective vampire throughput and queue growth rate |
    | Actual LLM node quality | Depends on Ollama model and temperature | Determines whether 15 nodes represent genuine topic breadth or generic variations |
    | Queue depth under load | Runtime Redis state | Cannot measure from static analysis; backpressure gap is an architectural risk, not a measurable value |

    These items are explicitly out of scope for Phase 06 static audit. A runtime smoke test would be required to verify them.

    ## Missing / Inflated Claims

    A list of specific places where claims exceed implementation:

    1. "Deep mine up to page 5" — The loop exists but breaks after the first page with any new URL. In a fresh mission, page 2 is never reached. The claim creates an expectation of breadth the logic does not deliver except at near-saturation. (SEARCH_BEHAVIOR_REPORT.md)
    2. "Topic taxonomy" — parent_node_id is never set at runtime; all nodes have parent_node_id = None; the graph is flat despite the schema supporting hierarchy. (TAXONOMY_GENERATION_AUDIT.md)
    3. "Academic URL filtering" — ACADEMIC_WHITELIST_DOMAINS exists but is used only for classification, not rejection. academic_only mode is wired but not activated. (URL_SELECTION_HEURISTICS.md)
    4. "4-mode epistemic cycling" — Cycling is correct within a session; exhausted_modes=set() on every restart means prior mode progress is discarded and GROUNDING re-executes on all nodes after each restart. (DISCOVERY_AUDIT.md)
    5. "Non-blocking architecture" (implicit) — enqueue_job is an unbounded rpush; a fast frontier can outrun 8 vampires with no backpressure mechanism. (DISCOVERY_AUDIT.md)

    ## Verdict

    **Status: PASS**

    The discovery layer is not thin search wrapping. AdaptiveFrontier implements LLM-driven node decomposition, epistemic cycling, query engineering, and respawn logic. Structure exists in schema and in prompt engineering. No area is a clean FAIL.

    The PARTIAL findings across all five claimed capabilities represent enforcement gaps — the mechanisms are present but incomplete in the runtime path. These are tracked as technical debt items rather than failures.

    The queue/backpressure gap (OPEN) is the highest operational risk because it is unbounded by design rather than by omission. It does not affect the correctness of individual URL discovery but affects system stability under active frontier runs.

    Phase 06 verdict: **PASS with five PARTIAL findings and one OPEN operational gap.**
  </action>

  <verify>
    <automated>
      grep "PASS" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/PHASE-06-VERIFICATION.md
      grep "PARTIAL" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/PHASE-06-VERIFICATION.md
      grep "Runtime-Only" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/PHASE-06-VERIFICATION.md
      grep "exhausted_modes" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/PHASE-06-VERIFICATION.md
    </automated>
  </verify>

  <done>
    PHASE-06-VERIFICATION.md exists with:
    - A checklist using [x]/[ ] markers for all 5 claimed capabilities
    - An evidence index table linking each claim to its audit document
    - A runtime-only items table listing 5 items that cannot be verified statically
    - A missing/inflated claims list with 5 numbered entries
    - An explicit overall verdict: PASS with five PARTIAL findings and one OPEN operational gap
  </done>
</task>

</tasks>

<verification>
After all three tasks complete, run these checks to confirm all 5 deliverables exist and contain required content:

```bash
# Confirm all 5 files exist
ls /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/DISCOVERY_AUDIT.md
ls /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/TAXONOMY_GENERATION_AUDIT.md
ls /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/SEARCH_BEHAVIOR_REPORT.md
ls /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/URL_SELECTION_HEURISTICS.md
ls /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/PHASE-06-VERIFICATION.md

# Confirm DISCOVERY_AUDIT.md has the classification table and verdict
grep -c "PARTIAL" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/DISCOVERY_AUDIT.md
grep "PASS" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/DISCOVERY_AUDIT.md

# Confirm TAXONOMY_GENERATION_AUDIT.md has the parent_node_id finding
grep "parent_node_id" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/TAXONOMY_GENERATION_AUDIT.md
grep "157" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/TAXONOMY_GENERATION_AUDIT.md

# Confirm SEARCH_BEHAVIOR_REPORT.md has the break inversion and engine inventory
grep "break" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/SEARCH_BEHAVIOR_REPORT.md
grep "google,bing" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/SEARCH_BEHAVIOR_REPORT.md

# Confirm URL_SELECTION_HEURISTICS.md documents academic_only as inactive
grep "academic_only" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/URL_SELECTION_HEURISTICS.md
grep "system.py" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/URL_SELECTION_HEURISTICS.md

# Confirm PHASE-06-VERIFICATION.md has all required sections
grep "Runtime-Only" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/PHASE-06-VERIFICATION.md
grep "PASS" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/PHASE-06-VERIFICATION.md
grep "exhausted_modes" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/PHASE-06-VERIFICATION.md
```
</verification>

<success_criteria>
All 5 deliverable files exist in `.planning/gauntlet_phases/phase06_discovery/`.

DISCOVERY_AUDIT.md contains a 7-row classification table with the exact classifications from the user-reviewed table, an overall verdict of PASS with PARTIAL findings, and per-area evidence citing file:line references.

TAXONOMY_GENERATION_AUDIT.md identifies parent_node_id never being set at runtime as the central finding, with frontier.py lines 157-171 and domain_schema.py line 107 cited explicitly.

SEARCH_BEHAVIOR_REPORT.md explains the break-on-first-success inversion clearly, includes the behavior table showing fresh vs. near-saturation vs. saturated mission behavior, and lists the 5 SearXNG engines from the payload.

URL_SELECTION_HEURISTICS.md documents that academic_only is wired (crawler.py line 185) but inactive at construction (system.py lines 125-128), and that ACADEMIC_WHITELIST_DOMAINS classifies but does not filter.

PHASE-06-VERIFICATION.md carries an explicit overall verdict (PASS with five PARTIAL findings and one OPEN operational gap), a runtime-only items table with 5 entries, and a missing/inflated claims list with 5 numbered entries.
</success_criteria>

<output>
After all tasks complete, create `.planning/gauntlet_phases/phase06_discovery/PHASE-06-SUMMARY.md` with:
- Files produced (list all 5)
- Classification table (copied from DISCOVERY_AUDIT.md)
- Overall verdict
- Any deviations from this plan
</output>
