# Search Behavior Report

## Claim Under Review

Discovery deep mines up to page 5 to find new URLs, providing genuine search depth beyond page 1.

## Page Loop Analysis — The Central Inversion

The loop in `discover_and_enqueue` (crawler.py lines 294-330) iterates `for page in range(1, 6)`, structurally supporting pages 1 through 5. The break condition at lines 322-326 reads:

```python
if page_new_count > 0:
    if page > 1:
        console.print(f"[dim][Crawler] Deep Mine successful on Page {page}. Found {page_new_count} new targets.[/dim]")
    break
```

This fires as soon as any page yields at least one URL not present in `visited_urls`. The loop stops at the first page with any new URL.

**What this actually means:** In a fresh mission where `visited_urls` is empty, every URL returned on page 1 is new. `page_new_count > 0` on page 1, so the loop always exits after page 1. Page 2 is never fetched in a fresh mission.

Pages 2-5 are only reached when pages 1 through N-1 are entirely exhausted duplicates — that is, every URL on those pages is already in `visited_urls`. This is a dedup fallback mechanism, not active depth exploration. The label "Deep Mine" and the comment `# Deep Mine: Page 1 to 5` at line 294 create an expectation of breadth that the break-on-first-success semantics do not deliver under normal operating conditions.

The complementary inner break at line 296-297 (`if not urls: break`) fires when `_search` returns an empty result set, handling the fully-saturated case.

### Behavior Table

| Mission State | Pages Actually Fetched | Reason |
|---------------|------------------------|--------|
| Fresh (visited_urls empty) | 1 | Every URL on page 1 is new; break fires immediately |
| Near-saturation (many known URLs) | 2-5 | Pages 1..N are all duplicates; loop continues until a new URL is found |
| Fully saturated | 1 (empty result) | _search returns nothing; inner break fires on line 297 |

## SearXNG Architecture

Three SearXNG instance URLs are hardcoded in `CrawlerConfig` (crawler.py lines 47-51):

```
http://127.0.0.1:8080
http://10.9.66.45:8080
http://10.9.66.154:8080
```

The `_search` method (lines 245-278) queries all three instances in parallel using `asyncio.as_completed`. The first instance to return a successful (HTTP 200) non-empty result set wins; the remaining tasks are cancelled (lines 272-277). The URLs list is shuffled with `random.shuffle` before task creation (line 269), providing load distribution across restarts.

The `pageno` parameter is correctly forwarded to SearXNG in the payload at lines 255-257:

```python
payload = {
    "q": query,
    "format": "json",
    "pageno": pageno,
    "engines": "google,bing,brave,duckduckgo,qwant"
}
```

The five general-purpose engines in the payload are: `google`, `bing`, `brave`, `duckduckgo`, `qwant`. These are standard web search engines. No academic-specific engines (Semantic Scholar API, PubMed, CORE, BASE, CrossRef) are included in the payload.

## Engine Inventory

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

**Note:** Whether the SearXNG instances at the configured addresses have Google Scholar or similar scholarly engines enabled as additional backends is a runtime-only question that cannot be determined from static analysis. The payload specifies only the 5 engines listed above.

## ResearchPolicy — Not Used in Engine Selection

`_frame_research_policy` (frontier.py lines 173-277) builds a `ResearchPolicy` object stored as `self.policy` with `subject_class` (e.g., `"investigative"`, `"scientific"`) and `authority_indicators` (preferred source classes) fields. Neither field is passed to `_search` (crawler.py lines 245-278) or included in the SearXNG payload construction (lines 252-257). The `ResearchPolicy` guides query tone via the decomposition and query engineering prompts but does not alter engine selection, domain targeting, or pageno behavior. The SearXNG call is identical regardless of whether the mission's policy is `"scientific"` or `"investigative"`.

## Classification

**PARTIAL / MISCHARACTERIZED** — the loop structure technically supports 5 pages, but the break-on-first-success semantics mean pages 2-5 are a dedup fallback, not active depth exploration. In a fresh mission, page 2 is never reached. The five-engine SearXNG integration is real and correctly implemented; specialized academic API access is not implemented. The claim of "deep mine up to page 5" is misleading in the normal operating regime.
