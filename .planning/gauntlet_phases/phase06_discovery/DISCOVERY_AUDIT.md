# Phase 06: Discovery Engine Audit

## Audit Method

This audit is based exclusively on static code inspection of the Sheppard V3 discovery layer. All findings cite specific file and line number. No runtime execution was performed. Visited URL persistence is treated as a resolved input: Phase 05B confirmed that `get_visited_urls` is correctly implemented and wired in `_load_checkpoint` (frontier.py line 150), removing it from the scope of open gaps. The audit covers five claimed capabilities and two additional areas identified during research: queue/backpressure and visited URL persistence.

## Classification Table

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

### Area 1: Taxonomic Decomposition

`frontier.py` line 203 prompts for exactly 15 nodes (`"node 1", "node 2", ..., "node 15"`), but lines 251-263 iterate `data.get('nodes', [])` with no minimum count enforcement. Lines 157-171 (`_save_node`) construct `MissionNode` without setting `parent_node_id`, which defaults to `None` for every node written. Lines 329-352 (`_respawn_nodes`) also call `_save_node` without passing `parent_node_id`. The hierarchy declared in `domain_schema.py` line 107 (`parent_node_id: Optional[str] = None`) is never populated at runtime. Node structure exists in schema and prompt; it does not exist in the DB rows written.

### Area 2: Search Depth / Deep Mining

`crawler.py` lines 294-330 implement a `for page in range(1, 6)` loop in `discover_and_enqueue`. The break condition at lines 322-326 reads: `if page_new_count > 0: break`. This fires immediately when any page yields at least one URL not in `visited_urls`. In a fresh mission where `visited_urls` is empty, every URL on page 1 is new, so `page_new_count > 0` on page 1 and the loop always exits after page 1. Pages 2-5 are only reached when pages 1 through N-1 are entirely exhausted duplicates — dedup fallback behavior, not active depth exploration.

### Area 3: URL Quality Controls

`ACADEMIC_WHITELIST_DOMAINS` (crawler.py lines 25-30) lists 13 entries: `.edu`, `.gov`, `arxiv.org`, `pubmed.ncbi.nlm.nih.gov`, `scholar.google.com`, `semanticscholar.org`, `acm.org`, `ieee.org`, `nature.com`, `science.org`, `springer.com`, `researchgate.net`, `ssrn.com`. `_is_academic(url)` (lines 385-387) checks substring membership and returns a boolean used only to set `source_type = "academic"` vs. `"web"` on `CrawlResult`. `_route_url` (lines 112-132) returns `"fast"` or `"slow"` for lane assignment; neither return value causes URL rejection. `academic_only` mode (line 185) would skip non-academic URLs, but it defaults to `False` (line 71) and is not set at construction in `system.py` lines 125-128. No filtering occurs in `discover_and_enqueue` (lines 294-330): every URL not in `visited_urls` is enqueued unconditionally.

### Area 4: Epistemic Modes

Four modes are defined at frontier.py lines 26-37: `GROUNDING`, `EXPANSION`, `DIALECTIC`, `VERIFICATION`. Mode selection (lines 286-291) iterates them in priority order, skipping exhausted modes. The selected mode is injected into the query engineering prompt at lines 294-310 as `MODE: {mode} ({MODES[mode]})`. However, `_load_checkpoint` (lines 141-148) reconstructs each `FrontierNode` with `exhausted_modes=set()` — a hardcoded empty set. There is no DB field queried for prior mode state. `MissionNode` (domain_schema.py lines 104-128) has no `exhausted_modes` field, so even if `_load_checkpoint` attempted to restore it, the data does not exist in the persisted schema. On every restart, all nodes appear to have consumed zero modes and `GROUNDING` re-executes on all nodes.

### Area 5: Obscure Source Discovery

The SearXNG payload (crawler.py lines 255-257) specifies `"engines": "google,bing,brave,duckduckgo,qwant"` — five general-purpose web engines. No academic-specific engines (Semantic Scholar API, PubMed, CORE, BASE, CrossRef) are called directly. The SearXNG instance pool (lines 47-51) configures three hardcoded URLs; first-success-wins via `asyncio.as_completed` (lines 265-278). `ResearchPolicy` fields `subject_class` and `authority_indicators` (set in `_frame_research_policy`) are not passed to `_search` or included in the SearXNG payload — policy guides query tone only.

### Area 6: Queue / Backpressure

`enqueue_job` in `redis.py` (lines 83-84) executes `rpush` with no prior `llen` check and no maximum queue depth configuration. `discover_and_enqueue` (crawler.py lines 294-330) calls `enqueue_job` for every new URL without checking current queue depth. With 15 initial nodes, 4 queries each, and ~10-20 SearXNG results per page, the frontier can enqueue ~900 jobs before any vampire finishes its first scrape. Eight vampires (system.py line 150) each block on `blpop` and then on HTTP to firecrawl-local with a 60-second timeout (crawler.py line 60). Budget excess causes re-enqueue (system.py lines 360-363), not drop, which can further inflate queue depth. There is no circuit-breaker.

### Area 7: Visited URL Persistence

`get_visited_urls` is implemented at `storage_adapter.py` lines 532-534 and correctly returns `{r["normalized_url"] for r in rows if r.get("normalized_url")}`. `_load_checkpoint` (frontier.py line 150) assigns the result to `self.visited_urls`. Phase 05B resolved the prior gap where `visited_urls` was always reset to `set()`. No FIXME remains in frontier.py on this path.

## Hard-Fail Assessment

| Hard-Fail Condition | Risk Level | Disposition |
|---------------------|------------|-------------|
| Discovery is just thin search wrapping with inflated claims | LOW | CLEARED — AdaptiveFrontier adds LLM-driven node decomposition, epistemic cycling, query engineering, and respawn logic; this is not a thin wrapper |
| Taxonomy generation is claimed but not enforced | MEDIUM | CLEARED — nodes are generated and used; parent_node_id gap is PARTIAL, not FAIL; fallback provides minimum 5 nodes |
| Search depth is claimed but not implemented | MEDIUM | CLEARED — the loop structure is real; the claim is misleading (break-on-first-success), not absent; classified as MISCHARACTERIZED |
| URL quality controls are absent | LOW-MEDIUM | CLEARED — ACADEMIC_WHITELIST_DOMAINS exists and classifies; academic_only is implemented; gap is inactive-at-construction, not absent |

## Overall Verdict

**Verdict: PASS with multiple PARTIAL findings**

No area is a clean FAIL: the structures, prompts, and logic exist in every case. No area is a clean PASS: enforcement is absent or incomplete in the runtime path for every claimed capability. The system is a well-architected discovery layer where schema design and prompt engineering are ahead of runtime enforcement. The queue/backpressure gap is the highest operational risk because it is unbounded by design — `rpush` with no depth limit and no circuit-breaker — rather than an oversight in an otherwise enforced system. All PARTIAL findings are tracked as technical debt items; none prevent individual URL discovery from functioning, but they each create correctness gaps at scale or across restarts.
