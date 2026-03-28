# Phase 06 Verification

## Discovery Claims Checklist

- [x] Taxonomic decomposition implemented
  Evidence: `_frame_research_policy` prompts for 15 nodes (frontier.py lines 200-215); node extraction iterates `data.get('nodes', [])` with cleaning (lines 251-263); fallback to 5 hardcoded nodes on LLM failure (lines 266-277). Node count not enforced after extraction; `parent_node_id` never set at runtime — all nodes written with `parent_node_id = None`. PARTIAL.

- [x] Epistemic modes defined and used
  Evidence: Four modes defined (frontier.py lines 26-37): GROUNDING, EXPANSION, DIALECTIC, VERIFICATION. Mode selection and injection implemented (lines 286-310); selected mode passed to query engineering prompt. `exhausted_modes` reset to `set()` on every restart (line 147 — hardcoded in `_load_checkpoint`). Schema has no `exhausted_modes` column (`MissionNode` at domain_schema.py lines 104-128). PARTIAL — state loss on resume.

- [x] Multi-page search structure present
  Evidence: Page loop `range(1,6)` in `discover_and_enqueue` (crawler.py lines 294-330). PARTIAL — break-on-first-success (`if page_new_count > 0: break` at lines 322-326) means pages 2-5 are dedup fallback. In a fresh mission, page 2 is never reached. See SEARCH_BEHAVIOR_REPORT.md.

- [x] Deduplication logic present
  Evidence: `visited_urls` check in `discover_and_enqueue` (crawler.py lines 300-302); `get_visited_urls` implemented at storage_adapter.py lines 532-534 (`{r["normalized_url"] for r in rows if r.get("normalized_url")}`); wired in `_load_checkpoint` (frontier.py line 150: `self.visited_urls = await self.sm.adapter.get_visited_urls(self.mission_id)`). VERIFIED PASS (Phase 05B).

- [x] URL quality infrastructure exists
  Evidence: `ACADEMIC_WHITELIST_DOMAINS` defined with 13 entries (crawler.py lines 25-30); `_is_academic` implemented (lines 385-387); `academic_only` mode implemented in `crawl_topic` (line 185). PARTIAL — whitelist classifies but does not filter; `academic_only` defaults to `False` and is not activated at construction (`system.py` lines 125-128 omit the argument).

## Evidence Index

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

The following items could not be verified by static analysis and require a live run to confirm:

| Item | Why Unverifiable Statically | Impact |
|------|----------------------------|--------|
| SearXNG engine config on instances | Configured in SearXNG admin UI, not in code | Determines whether scholarly engines (Google Scholar, Semantic Scholar, Unpaywall) are active on the three configured instances |
| SearXNG instance availability | Network-dependent | Affects whether any search results are returned; all three instances at hardcoded addresses may be unreachable |
| Firecrawl-local performance | Depends on running service | Determines effective vampire throughput and queue growth rate; blocked vampires inflate queue depth |
| Actual LLM node quality | Depends on Ollama model and temperature | Determines whether the 15 nodes represent genuine topic breadth or generic variations of the same concept |
| Queue depth under load | Runtime Redis state | Cannot measure from static analysis; backpressure gap is an architectural risk, not a measurable value from code |

These items are explicitly out of scope for Phase 06 static audit. A runtime smoke test would be required to verify them.

## Missing / Inflated Claims

1. **"Deep mine up to page 5"** — The loop exists but breaks after the first page with any new URL. In a fresh mission, page 2 is never reached. The claim creates an expectation of breadth the logic does not deliver except at near-saturation. (SEARCH_BEHAVIOR_REPORT.md)

2. **"Topic taxonomy"** — `parent_node_id` is never set at runtime; all nodes have `parent_node_id = None`; the graph is flat despite the schema supporting hierarchy. `_save_node` and `_respawn_nodes` both omit the parent reference at the DB write boundary. (TAXONOMY_GENERATION_AUDIT.md)

3. **"Academic URL filtering"** — `ACADEMIC_WHITELIST_DOMAINS` exists but is used only for classification, not rejection. `academic_only` mode is wired in `crawl_topic` but not activated at the system construction site. All URLs not in `visited_urls` are enqueued regardless of domain quality. (URL_SELECTION_HEURISTICS.md)

4. **"4-mode epistemic cycling"** — Cycling is correct within a single session. `exhausted_modes=set()` on every restart means prior mode progress is discarded and GROUNDING re-executes on all nodes after each restart. Schema has no column to persist mode history across sessions. (DISCOVERY_AUDIT.md)

5. **"Non-blocking architecture" (implicit)** — `enqueue_job` is an unbounded `rpush`; a fast frontier can outrun 8 vampires with no backpressure mechanism. Budget excess causes re-enqueue, not drop, which can further inflate queue depth. (DISCOVERY_AUDIT.md)

## Verdict

**Status: PASS**

The discovery layer is not thin search wrapping. `AdaptiveFrontier` implements LLM-driven node decomposition, epistemic cycling, query engineering, and respawn logic. Structure exists in schema and in prompt engineering. No area is a clean FAIL.

The PARTIAL findings across all five claimed capabilities represent enforcement gaps — the mechanisms are present but incomplete in the runtime path. These are tracked as technical debt items rather than failures. The structures exist; the enforcement does not consistently reach the DB write boundary or the system construction site.

The queue/backpressure gap (OPEN) is the highest operational risk because it is unbounded by design rather than by omission. It does not affect the correctness of individual URL discovery but affects system stability under active frontier runs where firecrawl-local is slow or saturated.

Phase 06 verdict: **PASS with five PARTIAL findings and one OPEN operational gap.**
