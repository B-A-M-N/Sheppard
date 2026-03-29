# Phase 06: Discovery Engine Verification — Research

**Researched:** 2026-03-27
**Domain:** Research acquisition layer — AdaptiveFrontier, FirecrawlLocalClient, SearXNG integration, Redis queue coupling
**Confidence:** HIGH (all findings verified by reading primary source files)

---

## Summary

Phase 06 is an audit of whether the discovery layer does what it claims: structured topic expansion, multi-page deep mining, URL quality controls, epistemic mode cycling, and access to obscure/specialized sources. Findings below are drawn exclusively from reading the live source files — `frontier.py`, `crawler.py`, `system.py`, `storage_adapter.py`, and `domain_schema.py`.

The overall picture is a well-architected system where structure exists in schema and in prompt engineering, but enforcement is absent or incomplete in the runtime path. The most important operational gaps are: (1) `exhausted_modes` is always reset to empty on resume, meaning epistemic cycling cannot survive a restart; (2) `parent_node_id` is never populated at runtime, so the node graph is flat even though the schema supports hierarchy; (3) the search "deep mine" breaks on the first page that yields any new URL — multi-page pagination is a dedup fallback, not genuine depth exploration; and (4) `enqueue_job` is an unbounded `rpush` with no queue-depth check, so a fast frontier can outrun 8 vampire consumers with no backpressure.

**Primary recommendation:** Classify the discovery layer as PARTIAL across all five claims. No single claim is a clean FAIL (the structures exist) and no single claim is a clean PASS (enforcement is absent or broken). The queue/backpressure gap is the highest operational risk because it is unbounded by design rather than by omission.

---

## Area 1: Taxonomic Decomposition

### Claim
Discovery is driven by structured, LLM-generated research nodes representing a topic taxonomy, not flat keyword search.

### What the code actually does

**Prompt — `_frame_research_policy` (frontier.py lines 200–215):**

The prompt sent to the LLM asks for:
1. Evidence stack definition
2. Authority definition
3. "15 foundational, highly specific research nodes to explore"

The exact target count is hardcoded in the prompt: `"node 1", "node 2", ..., "node 15"`. The LLM may return fewer or more; the code iterates `data.get('nodes', [])` without enforcing a minimum or maximum count.

**Node name cleaning (lines 253–258):**
Each node string is cleaned with `re.sub(r'^(Node\s*\d+:?|\d+[\.\)]\s*)', '', n, ...)`. Only names longer than 3 characters are accepted.

**Fallback (lines 266–277):**
If LLM generation fails or JSON parse fails, exactly 5 hardcoded fallback nodes are used:
```
[topic_name]
[topic_name] technical architecture
[topic_name] implementation details
[topic_name] failure modes
[topic_name] best practices
```

**`parent_node_id` — MissionNode schema vs. runtime:**
`MissionNode` (domain_schema.py line 107) declares `parent_node_id: Optional[str] = None`.
In `_save_node` (frontier.py lines 163–171), the `MissionNode` is constructed WITHOUT setting `parent_node_id` — it defaults to `None` for every node written. In `_respawn_nodes` (lines 329–352), child nodes are spawned but their `_save_node` call also does not pass `parent_node_id`. The parent-child relationship exists in schema; it is never populated at runtime.

### Classification: PARTIAL

Structure present. Prompt targets 15 nodes. Node cleaning and fallback implemented. `parent_node_id` field in schema never populated — the node graph is flat at runtime. Enforcement of node count and topic specificity depends entirely on LLM response quality.

**Key line numbers:**
- Decomposition prompt: frontier.py lines 200–215
- Node extraction loop: frontier.py lines 251–263
- Fallback nodes: frontier.py lines 266–277
- `_save_node` — no `parent_node_id`: frontier.py lines 157–171
- `_respawn_nodes` — no `parent_node_id` in child save: frontier.py lines 329–352
- `MissionNode.parent_node_id` field: domain_schema.py line 107

---

## Area 2: Search Depth / Deep Mining

### Claim
Discovery deep mines up to page 5 to find new URLs, providing genuine search depth beyond page 1.

### What the code actually does

**`discover_and_enqueue` loop (crawler.py lines 294–331):**

```python
for page in range(1, 6):  # Deep Mine: Page 1 to 5
    urls = await self._search(query, pageno=page)
    if not urls:
        break

    page_new_count = 0
    for url in urls:
        if visited_urls is not None and url in visited_urls:
            continue
        # ... enqueue ...
        page_new_count += 1

    if page_new_count > 0:
        if page > 1:
            console.print(...)  # "Deep Mine successful on Page N"
        break  # ← BREAK ON FIRST SUCCESS
    else:
        continue  # only go deeper if page was all duplicates
```

**The break condition is: stop as soon as any page yields at least one new URL.**

This means "deep mining" is not forward-depth exploration. It is a dedup fallback: if page 1 is entirely already-visited URLs, try page 2, and so on. In a fresh mission with an empty `visited_urls`, the loop always exits after page 1 because every URL on page 1 is new. Genuine multi-page depth is only triggered when pages 1 through N-1 are exhausted duplicates.

**`_search` — first-wins SearXNG race (crawler.py lines 245–278):**
Three SearXNG instances are queried in parallel with `asyncio.as_completed`. The first successful response is used; remaining tasks are cancelled. The `pageno` parameter is forwarded correctly to SearXNG.

### Classification: PARTIAL / MISCHARACTERIZED

The loop structure technically supports up to 5 pages, but the break-on-first-success logic means pages 2–5 are a dedup fallback, not active depth exploration. In practice, a new mission always exits after page 1. The claim of "deep mine up to page 5" creates an expectation of breadth that the logic does not deliver unless the mission is near-saturation.

**Key line numbers:**
- Loop: crawler.py lines 294–331
- Break condition (page_new_count > 0): crawler.py lines 323–326
- SearXNG race: crawler.py lines 265–278
- pageno passed to SearXNG: crawler.py lines 255–257

---

## Area 3: URL Quality Controls

### Claim
URL quality is filtered using an academic whitelist; non-relevant URLs are rejected.

### What the code actually does

**`ACADEMIC_WHITELIST_DOMAINS` (crawler.py lines 25–30):**
```python
ACADEMIC_WHITELIST_DOMAINS: Set[str] = {
    ".edu", ".gov", "arxiv.org", "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com", "semanticscholar.org", "acm.org",
    "ieee.org", "nature.com", "science.org", "springer.com",
    "researchgate.net", "ssrn.com",
}
```

**`_is_academic(url)` (crawler.py lines 385–387):**
Returns `True` if any whitelist entry appears in the domain. Used to set `source_type = "academic"` vs. `"web"` on `CrawlResult`.

**`_route_url(url)` (crawler.py lines 112–132):**
Returns `"fast"` or `"slow"`. The `"slow"` lane routes PDFs and known static domains to Redis offload. This is a processing-lane decision, not a rejection. `_route_url` never returns a value that causes a URL to be dropped or skipped.

**`academic_only` mode (crawler.py line 185):**
In `crawl_topic`, if `self.academic_only` is `True`, non-academic URLs are skipped. However, `academic_only` defaults to `False` (line 71) and is not set to `True` in `system.py` when constructing `FirecrawlLocalClient` (system.py line 125–128). This mode is wired but inactive.

**In `discover_and_enqueue`:**
There is no call to `_is_academic` and no filtering of any kind before enqueuing. Every URL that is not in `visited_urls` is enqueued to `queue:scraping`.

### Classification: PARTIAL (classification without filtering/rejection)

`ACADEMIC_WHITELIST_DOMAINS` exists and is used to classify URLs by source type. It does not filter or reject URLs. `academic_only` mode is implemented but disabled at the construction site. All URLs passing the `visited_urls` check are enqueued regardless of domain quality.

**Key line numbers:**
- `ACADEMIC_WHITELIST_DOMAINS` definition: crawler.py lines 25–30
- `_is_academic`: crawler.py lines 385–387
- `_route_url` — no rejection, lane only: crawler.py lines 112–132
- `academic_only` default False: crawler.py line 71
- `academic_only` not set in system.py: system.py lines 125–128
- No filtering in `discover_and_enqueue`: crawler.py lines 294–331

---

## Area 4: Epistemic Modes

### Claim
Discovery cycles through 4 epistemic modes (GROUNDING, EXPANSION, DIALECTIC, VERIFICATION) per node, ensuring multi-angle coverage.

### What the code actually does

**Four modes defined (frontier.py lines 26–37):**
```python
EpistemicMode.GROUNDING    = "grounding"
EpistemicMode.EXPANSION    = "expansion"
EpistemicMode.DIALECTIC    = "dialectic"
EpistemicMode.VERIFICATION = "verification"
```

**Selection order (frontier.py lines 286–291):**
```python
for mode in [EpistemicMode.GROUNDING, EpistemicMode.VERIFICATION,
             EpistemicMode.DIALECTIC, EpistemicMode.EXPANSION]:
    if mode not in node.exhausted_modes:
        return node, mode
```
Modes are iterated in a fixed priority order. A mode is added to `exhausted_modes` after execution (line 125). When all 4 modes are exhausted for a node, the node is marked `"saturated"` (lines 290–292).

The mode is injected into the query engineering prompt (frontier.py lines 294–310) as `MODE: {mode} ({MODES[mode]})`, guiding query tone.

**`exhausted_modes` restoration in `_load_checkpoint` (frontier.py lines 141–155):**

```python
for n in db_nodes:
    self.nodes[n['label']] = FrontierNode(
        concept=n['label'],
        status=n['status'],
        yield_history=[],       # comment: "Omitting complex unpack for now"
        exhausted_modes=set()   # HARDCODED EMPTY SET
    )
```

`exhausted_modes` is hardcoded to `set()` on every load. There is no DB field queried for this value. On restart, every node appears to have consumed zero modes, and the frontier re-executes GROUNDING on every node regardless of what was already run.

**What is stored vs. what is restored:**
`_save_node` stores a `MissionNode` via `upsert_mission_node`. `MissionNode` (domain_schema.py) has no `exhausted_modes` or equivalent field. The information is discarded at the DB boundary. Even if `_load_checkpoint` tried to restore it, the data does not exist in the persisted schema.

### Classification: PARTIAL (state loss on resume)

Four modes are defined, selected, and passed to the query prompt. The cycling logic is correct within a single session. On any restart, `exhausted_modes` is reset to empty and all prior mode progress is lost. The schema has no column to persist mode history.

**Key line numbers:**
- Mode definitions: frontier.py lines 26–37
- Mode selection loop: frontier.py lines 286–291
- Mode injection into query prompt: frontier.py lines 294–310
- `exhausted_modes` hardcoded `set()` in `_load_checkpoint`: frontier.py lines 143–148
- `_save_node` — no `exhausted_modes` field: frontier.py lines 157–171
- `MissionNode` — no `exhausted_modes` field: domain_schema.py lines 104–128

---

## Area 5: Obscure Source Discovery

### Claim
Discovery accesses specialized, obscure academic and technical sources beyond standard web search.

### What the code actually does

**SearXNG engine configuration (crawler.py lines 255–257):**
```python
payload = {
    "q": query,
    "format": "json",
    "pageno": pageno,
    "engines": "google,bing,brave,duckduckgo,qwant"
}
```

Five general-purpose search engines are configured. No academic-specific engines (Semantic Scholar API, PubMed API, CORE, BASE, CrossRef) are called directly. No domain-specific override based on `ResearchPolicy.subject_class` or `authority_indicators`.

**SearXNG instance pool (crawler.py lines 47–51):**
Three hardcoded SearXNG instance URLs are configured. First-success-wins strategy is used. Whether those SearXNG instances have scholarly engines enabled (Google Scholar, Semantic Scholar, Unpaywall, etc.) is a runtime configuration matter — it cannot be verified statically.

**`ResearchPolicy` not used in search construction:**
`self.policy` (set in `_frame_research_policy`) contains `subject_class` and `authority_indicators` fields. Neither is passed to `_search` or to the SearXNG payload. The policy guides query tone via the prompt, but not the search engine selection or domain targeting.

### Classification: PARTIAL (multi-engine SearXNG, not domain-specialized)

Multi-instance SearXNG with 5 general web engines is implemented. No specialized academic API calls. Policy information is not used to select engines. Whether SearXNG instances are configured with scholarly engines is a runtime-only question.

**Runtime-only items (cannot be verified statically):**
- SearXNG engine configuration (e.g., whether Google Scholar, Semantic Scholar, or Unpaywall engines are enabled on the instances at `127.0.0.1:8080`, `10.9.66.45:8080`, `10.9.66.154:8080`)
- Whether SearXNG instances are reachable and returning results

**Key line numbers:**
- SearXNG engine list in payload: crawler.py lines 255–257
- SearXNG instance pool: crawler.py lines 47–51
- First-success-wins race: crawler.py lines 268–278
- `ResearchPolicy` fields not used in `_search`: crawler.py lines 245–278

---

## Area 6: Queue / Backpressure (New — missing from prior analysis)

### Claim (implicit)
Discovery enqueues URLs at a rate vampires can consume; no runaway queue growth.

### What the code actually does

**`enqueue_job` — unbounded `rpush` (redis.py line 84):**
```python
async def enqueue_job(self, queue_name: str, payload: JsonDict) -> None:
    await self.client.rpush(queue_name, self._serialize(payload))
```

`rpush` on a Redis list is unbounded. There is no `llen` check before push. There is no maximum queue depth configuration.

**Frontier production rate:**
- Up to 15 initial nodes, each generating 4 queries (3 LLM + 1 raw concept anchor), each query hitting up to 1 SearXNG page (more only on dedup saturation).
- SearXNG typically returns 10–20 results per page.
- `_respawn_nodes` fires when `round_yield >= 5`, spawning 3–5 new nodes.
- Production rate is approximately: active_nodes × 4 queries × ~10–20 URLs per query.

**Vampire consumption rate:**
- 8 vampire tasks (system.py line 150), each blocking on `blpop` with a 10-second timeout.
- Each vampire performs one `_scrape_with_retry` call per job, which blocks on HTTP to firecrawl-local.
- If firecrawl-local is slow or saturated, each vampire can be blocked for up to 60 seconds per URL (CrawlerConfig.request_timeout = 60).

**Budget check position:**
Vampires check `self.budget.can_crawl(mission_id)` before scraping (system.py line 360). On budget excess, the job is re-enqueued (line 362), not dropped. This returns the job to the tail of the queue, which can cause queue depth to grow further if budget is exceeded but the frontier keeps producing.

**No queue-depth check before enqueue:**
`discover_and_enqueue` does not call any queue-length check before calling `system_manager.adapter.enqueue_job`. There is no circuit-breaker.

### Classification: GAP — No Backpressure

The frontier is an unthrottled producer. The Redis list is unbounded. 8 vampires each blocked for up to 60s per URL can drain at most ~480 URLs/minute under ideal conditions. A single frontier run with 15 nodes × 4 queries × 15 URLs = 900 jobs enqueued before any vampire has finished one job. With `_respawn_nodes` triggering on yield >= 5, the queue depth can grow faster than it is drained. Under a slow firecrawl-local, queue depth is unbounded for the lifetime of the mission.

The only natural bound on queue growth is `visited_urls` dedup — once all SearXNG results are in `visited_urls`, production stops. This works correctly at saturation but provides no flow control during the active growth phase.

**Key line numbers:**
- `enqueue_job` — `rpush` with no size check: redis.py lines 83–84
- `discover_and_enqueue` — no queue depth check: crawler.py lines 280–331
- Vampire count: system.py line 150
- Budget check position (post-dequeue, not pre-enqueue): system.py lines 360–363
- `request_timeout = 60`: crawler.py line 58

---

## Area 7: Visited URL Persistence

### Claim
Phase 05B resolved the gap where `visited_urls` was always reset to `set()` on restart.

### Verification (from phase05b SUMMARY.md and live code)

`get_visited_urls` is implemented in two places:
1. `CorpusStore` protocol stub: storage_adapter.py line 92
2. `SheppardStorageAdapter` concrete impl: storage_adapter.py lines 532–534

```python
async def get_visited_urls(self, mission_id: str) -> set[str]:
    rows = await self.list_sources(mission_id)
    return {r["normalized_url"] for r in rows if r.get("normalized_url")}
```

`_load_checkpoint` (frontier.py line 150) assigns:
```python
self.visited_urls = await self.sm.adapter.get_visited_urls(self.mission_id)
```

No FIXME remains in frontier.py.

### Classification: VERIFIED INPUT CONDITION (resolved by Phase 05B)

Visited URL persistence is correctly implemented and wired. This area is not a Phase 06 finding.

**Key line numbers:**
- Protocol stub: storage_adapter.py line 92
- Concrete impl: storage_adapter.py lines 532–534
- Wired in `_load_checkpoint`: frontier.py line 150

---

## Hard-Fail Risk Assessment

The Phase 06 spec defines 4 hard-fail conditions:

| Hard-Fail Condition | Risk Level | Evidence |
|---------------------|------------|----------|
| Discovery is just thin search wrapping with inflated claims | LOW | AdaptiveFrontier is not thin: it has LLM-driven node decomposition, epistemic cycling, query engineering, and respawn. The wrapper adds real structure. |
| Taxonomy generation is claimed but not enforced | MEDIUM | 15-node decomposition is prompted but count is not enforced. LLM may return fewer. Fallback is 5 nodes. Parent-child hierarchy is never populated. This is PARTIAL, not FAIL — the nodes exist and are used. |
| Search depth is claimed but not implemented | MEDIUM | The page-5 deep mine claim is misleading. The loop exists but breaks on first page with any new URL. In a fresh mission, page 2 is never reached. The claim is technically true but operationally mischaracterized. |
| URL quality controls are absent | LOW-MEDIUM | `ACADEMIC_WHITELIST_DOMAINS` exists and classifies URLs. `academic_only` mode is implemented. Neither filters or rejects during discovery. "Present but inactive" is PARTIAL, not FAIL. |

No single condition is a clean hard-fail by the strict definition. The audit verdict is expected to be PARTIAL across all areas.

---

## Runtime-Only Items (Cannot Be Verified Statically)

| Item | Why Unverifiable | Impact |
|------|-----------------|--------|
| SearXNG engine config on instances | Configured in SearXNG admin UI, not in code | Determines whether scholarly engines (Google Scholar, Semantic Scholar) are active |
| SearXNG instance availability | Network-dependent | Affects whether any search results are returned |
| Firecrawl-local performance | Depends on running service | Determines effective vampire throughput and queue growth rate |
| Actual LLM node quality | Depends on Ollama model and temperature | Determines whether the 15 nodes represent genuine topic breadth or generic variations |
| Queue depth under load | Runtime Redis state | Cannot measure from static analysis |

---

## Classification Summary

| Area | Classification | Root Cause of PARTIAL |
|------|---------------|----------------------|
| Taxonomic decomposition | PARTIAL | Node count not enforced; `parent_node_id` never set at runtime |
| Search depth / deep mining | PARTIAL / MISCHARACTERIZED | Break-on-first-success means pages 2–5 are dedup fallback, not depth |
| URL quality controls | PARTIAL | Whitelist classifies but does not filter; `academic_only` inactive |
| Epistemic modes | PARTIAL | `exhausted_modes` hardcoded `set()` on resume; schema has no column for it |
| Obscure source discovery | PARTIAL | Multi-engine SearXNG only; no specialized API calls; policy not used in engine selection |
| Queue / backpressure | GAP | `rpush` unbounded; no pre-enqueue depth check; frontier can outrun 8 vampires |
| Visited URL persistence | VERIFIED PASS | Phase 05B resolved this; correctly wired |

---

## Sources

All findings are from direct source code reads at commit state as of 2026-03-27:

- `/home/bamn/Sheppard/src/research/acquisition/frontier.py` — full file
- `/home/bamn/Sheppard/src/research/acquisition/crawler.py` — full file
- `/home/bamn/Sheppard/src/core/system.py` — lines 75–480
- `/home/bamn/Sheppard/src/memory/storage_adapter.py` — lines 470–894
- `/home/bamn/Sheppard/src/memory/adapters/redis.py` — lines 80–104
- `/home/bamn/Sheppard/src/research/domain_schema.py` — full file
- `/home/bamn/Sheppard/.planning/gauntlet_phases/phase05b_visited_urls/SUMMARY.md` — 05B verification

**Confidence breakdown:**
- All claims: HIGH — every finding is a direct code observation with line numbers, not inference
- Queue/backpressure throughput estimate: MEDIUM — the arithmetic is correct but actual runtime behavior depends on firecrawl-local response times which are not statically verifiable

**Research date:** 2026-03-27
**Valid until:** Code changes in the listed files invalidate specific findings
