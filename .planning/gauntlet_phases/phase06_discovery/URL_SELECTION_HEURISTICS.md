# URL Selection Heuristics Audit

## Claim Under Review

URL quality is filtered using an academic whitelist; non-relevant URLs are rejected.

## ACADEMIC_WHITELIST_DOMAINS

`ACADEMIC_WHITELIST_DOMAINS` is defined at crawler.py lines 25-30:

```python
ACADEMIC_WHITELIST_DOMAINS: Set[str] = {
    ".edu", ".gov", "arxiv.org", "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com", "semanticscholar.org", "acm.org",
    "ieee.org", "nature.com", "science.org", "springer.com",
    "researchgate.net", "ssrn.com",
}
```

The constant contains 13 entries: two TLD suffixes (`.edu`, `.gov`) and 11 specific domain strings.

`_is_academic(url)` (crawler.py lines 385-387) checks whether any whitelist entry appears as a substring in the parsed domain:

```python
def _is_academic(self, url: str) -> bool:
    domain = urlparse(url).netloc.lower()
    return any(domain.endswith(whitelist) or whitelist in domain for whitelist in ACADEMIC_WHITELIST_DOMAINS)
```

The return value of `_is_academic` is used only to set `source_type = "academic"` vs. `"web"` on `CrawlResult` metadata. It does not gate, reject, or filter any URL. The classification is informational only.

## _route_url — Lane Assignment, Not Rejection

`_route_url` (crawler.py lines 112-132) accepts a URL and returns either `"fast"` or `"slow"`. The two lanes route URLs to different processing paths: `"fast"` goes directly to the firecrawl scrape pipeline; `"slow"` routes PDFs and known high-latency domains (Wikipedia, arXiv, GitHub, etc.) to Redis offload via `_offload_to_slow_lane`.

`_route_url` never returns a value that causes a URL to be dropped or skipped. Every URL that enters `_route_url` gets a lane assignment and proceeds. This is a processing-lane decision, not a quality filter. The distinction matters:

- **Classification** (via `_is_academic`): labels a URL as academic or web, does not affect enqueue decision
- **Lane assignment** (via `_route_url`): determines processing path, does not affect whether URL is enqueued

Neither function implements rejection.

## academic_only Mode — Wired but Inactive

The `academic_only` flag is declared in `crawl_topic` (crawler.py line 185):

```python
if self.academic_only and not self._is_academic(url):
    discovery_queue.task_done(); continue
```

When `academic_only` is `True`, non-academic URLs are skipped during `crawl_topic` processing. This is the correct location and correct semantics for the filtering behavior the claim describes.

However:

- The default value of `academic_only` is `False` (crawler.py line 71: `academic_only: bool = False` in `FirecrawlLocalClient.__init__`)
- `FirecrawlLocalClient` is constructed in `system.py` at lines 125-128 as:

```python
self.crawler = FirecrawlLocalClient(
    config=CrawlerConfig(),
    on_bytes_crawled=self.budget.record_bytes,
)
```

The `academic_only` keyword argument is not passed. Python uses the default value of `False`. Therefore, `academic_only` mode is implemented in the crawler but is never activated via the system construction path.

**Result:** All URLs that pass the `visited_urls` check are enqueued to `queue:scraping` regardless of academic classification. The `academic_only` flag is dead code in the system construction path.

## discover_and_enqueue — No Quality Gate

In `discover_and_enqueue` (crawler.py lines 294-330), there is no call to `_is_academic` and no domain filtering before `enqueue_job`. The enqueue decision is made at lines 300-318: for each URL not in `visited_urls`, the URL is routed (lane assignment only) and then enqueued unconditionally. No quality check on domain type, academic classification, or whitelist membership is performed before the `enqueue_job` call at line 313.

Every URL not in `visited_urls` is enqueued to `queue:scraping` regardless of its domain.

## Queue / Backpressure Note

`enqueue_job` (redis.py lines 83-84) executes `await self.client.rpush(queue_name, self._serialize(payload))` — an unbounded `rpush` with no `llen` check before push and no maximum queue depth configuration. This is an operational risk distinct from URL quality but directly related to discovery enqueue behavior: because there is no quality gate before `enqueue_job`, any URL the frontier discovers is immediately enqueued regardless of relevance or domain quality. Cross-reference: this gap is classified as OPEN in DISCOVERY_AUDIT.md.

## Classification

**PARTIAL** — `ACADEMIC_WHITELIST_DOMAINS` exists and correctly classifies URLs by source type. It does not filter or reject URLs. `academic_only` mode is implemented and correctly placed in `crawl_topic`, but it is disabled at the system construction site (`system.py` lines 125-128 do not pass `academic_only=True`). URL quality controls are present as infrastructure but inactive in the runtime path. All URLs passing the `visited_urls` check are enqueued unconditionally.

## What Would Constitute PASS

- `academic_only=True` set during `FirecrawlLocalClient` construction (system.py lines 125-128) for missions requiring academic filtering, or a per-mission flag passed through from the mission configuration and wired into the constructor call
- A pre-enqueue domain quality check in `discover_and_enqueue` (before the `enqueue_job` call at line 313) that calls `_is_academic` or applies a reject list, so that URL filtering occurs at the frontier production boundary rather than inside the per-URL scrape path
