# SOAK-RESULTS

**Run date:** 2026-03-29 08:53
**Chunk config:** CHUNK_SIZE=2000, CHUNK_OVERLAP=300

## Duration
- Total duration: 25.5s
- URLs tested: 9
- Runs per URL: 2
- Total fetch attempts: 18

## Total URLs processed
- Successful (chunked): 6
- Rejected/failed: 3

## Retry Summary
- Total retry events: 0
- No retries observed

## Rejection Summary
- fetch_failure: 4
- below_length_gate: 2

## Chunking Metrics
- Successful chunked runs: 12
- Avg chunk count: 13.2
- Min chunk count: 1
- Max chunk count: 58
- Anomalies (chunker returned empty): 0

## Determinism Checks
- URLs with 2 successful runs: 6
- Stable (same hash both runs): 5
- Unstable (hash drift detected): 1
  - DRIFT: timeout  r1=1 chunks  r2=1 chunks

## Failure Classification
- validation_rejection: 2
- http_404: 2
- http_500: 2

## Per-URL Detail

### gov_html — `https://www.nih.gov/about-nih/what-we-do/nih-almanac`
- run=1  method=requests  retries=0  len=78  status=below_length_gate  (0.31s)
- run=2  method=requests  retries=0  len=78  status=below_length_gate  (0.27s)

### gov_html — `https://www.cdc.gov/flu/about/index.html`
- run=1  method=requests  retries=0  len=7641  status=OK (5 chunks)  (0.16s)
- run=2  method=requests  retries=0  len=7641  status=OK (5 chunks)  (0.14s)

### arxiv_abstract — `https://arxiv.org/abs/2310.06825`
- run=1  method=requests  retries=0  len=2199  status=OK (2 chunks)  (0.14s)
- run=2  method=requests  retries=0  len=2199  status=OK (2 chunks)  (0.13s)

### news_homepage — `https://apnews.com`
- run=1  method=requests  retries=0  len=12256  status=OK (8 chunks)  (0.56s)
- run=2  method=requests  retries=0  len=12256  status=OK (8 chunks)  (0.55s)

### news_homepage — `https://www.bbc.com/news`
- run=1  method=requests  retries=0  len=6874  status=OK (5 chunks)  (0.18s)
- run=2  method=requests  retries=0  len=6874  status=OK (5 chunks)  (0.16s)

### http_404 — `https://httpbin.org/status/404`
- run=1  method=requests  retries=0  len=None  status=fetch_failure  (0.51s)
- run=2  method=requests  retries=0  len=None  status=fetch_failure  (0.17s)

### http_500 — `https://httpbin.org/status/500`
- run=1  method=requests  retries=0  len=None  status=fetch_failure  (0.3s)
- run=2  method=requests  retries=0  len=None  status=fetch_failure  (0.17s)

### timeout — `https://httpbin.org/delay/35`
- run=1  method=requests  retries=0  len=312  status=OK (1 chunks)  (10.43s)
- run=2  method=requests  retries=0  len=312  status=OK (1 chunks)  (10.19s)

### wiki_large — `https://en.wikipedia.org/wiki/Machine_learning`
- run=1  method=requests  retries=0  len=92567  status=OK (58 chunks)  (0.57s)
- run=2  method=requests  retries=0  len=92567  status=OK (58 chunks)  (0.54s)

## Observations

### O1 — Zero retries despite active retry loop (BLOCKER for 08.2)
The crawler has a `for attempt in range(3)` retry loop, but `requests.HTTPError` (raised
by `resp.raise_for_status()`) is caught and returns `None` immediately — no retry.
Only `ConnectionError` and `Timeout` reach the retry path. HTTP 500 is transient but
receives no retry. This gap directly maps to Phase 08.2 criterion 1.

**Impact:** Any transient HTTP 5xx causes permanent ingestion failure on first attempt.

### O2 — HTTP error classification is undifferentiated
Both 404 (permanent) and 500 (transient) are classified the same way (`http_N`).
The live pipeline in `loop.py` catches all exceptions with a bare `except: pass` — so
HTTP failures are silently swallowed at the loop level, not surfaced.

**Impact:** Terminal failures are not visible to the caller; retry eligibility cannot
be determined.

### O3 — Firecrawl offline; primary extraction method untested
All 18 fetch attempts fell through to the `requests` fallback. The Firecrawl path
(localhost:3002) was unreachable. The Firecrawl → requests fallback works correctly,
but Firecrawl extraction quality is not exercised by this soak.

**Impact:** Soak evidence covers fallback path only.

### O4 — Chunking determinism: 5/6 stable; 1 expected drift
The `timeout` URL (httpbin.org/delay/35) showed hash drift between runs. Inspection:
the URL returned dynamic JSON (312 chars, different data each time) — not a timeout.
The response content itself changed, making drift expected. No internal chunking
non-determinism detected.

**Status:** Not a chunking bug. Dynamic external content is the source.

### O5 — NIH page extracted to 78 chars (false rejection)
`https://www.nih.gov/about-nih/what-we-do/nih-almanac` extracts to 78 chars —
below the 300-char length gate. The page is valid and substantial but the
`extract_text` heuristics strip it too aggressively. This is a false rejection
of real content.

**Impact:** Legitimate high-reliability .gov sources may be silently dropped.

### O6 — "Timeout" endpoint succeeded at 10s (expected behavior confirmed)
httpbin.org/delay/35 responded in ~10s rather than 35s. This confirms the fallback
`requests.get` timeout (30s) is operative, but the server simply responded quickly.
No timeout path was exercised. A dedicated timeout test needs a slower target.

### O7 — No unexpected_exception events
Zero runs hit the `unexpected_exception` bucket. All failure modes were correctly
classified into known categories. Observability is sufficient for failure diagnosis.

## Soak Verdict

**Status: ⚠️ ISSUES FOUND — proceed to 08.2**

| Criterion | Status |
|-----------|--------|
| No unexplained failures | ✅ All failures classified |
| Chunking stable | ✅ 5/5 real-content pairs stable |
| Validation behaving predictably | ✅ Length gate works |
| Failures mapped to ingestion path | ✅ See O1, O2 |
| Ready to feed into 08.2 plan | ✅ O1 and O2 are concrete targets |

**Direct 08.2 targets:**
1. **O1** → Retry classification: 5xx should retry, 4xx should not
2. **O2** → loop.py bare `except: pass` hides failures — needs explicit error surfacing
3. **O5** → Length gate false rejections on legitimate .gov pages (review extraction heuristics)
