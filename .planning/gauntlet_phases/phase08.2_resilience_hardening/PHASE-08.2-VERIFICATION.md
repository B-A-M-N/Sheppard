# Phase 08.2 Verification Results

**Date:** 2026-03-29
**Plan:** 08.2-01 Resilience Hardening
**Status:** PASS

---

## Observation Status

| Observation | Description | Status |
|-------------|-------------|--------|
| O1 | HTTP 5xx gets zero retries | PASS |
| O2 | loop.py silently swallows exceptions with bare `except: pass` | PASS |
| O5 | extract_text falsely rejects structured .gov pages | PASS |

---

## O1: Retry Classification

**Finding:** HTTP 5xx errors were caught immediately and returned None with no retry.
**Fix:** Replaced flat try/except with `for attempt in range(3)` retry loop in crawler.py.

**Behavior after fix:**
- HTTP 5xx: retries with linear backoff (1s, 2s) — up to 3 total attempts
- HTTP 4xx: returns None immediately (no retry — permanent errors)
- ConnectionError / Timeout: retries with linear backoff — up to 3 total attempts
- After 3 failed attempts: returns None (bounded, no infinite loop)
- `import time` added at module level

**Grep checks:**
```
grep -c "for attempt in range" src/research/archivist/crawler.py   -> 1  PASS
grep -c "HTTPError" src/research/archivist/crawler.py               -> 1  PASS
grep "500 <= status_code < 600" src/research/archivist/crawler.py   -> MATCH  PASS
grep -c "ConnectionError.*Timeout" src/research/archivist/crawler.py -> 1  PASS
```

---

## O2: Silent Exception Swallowing

**Finding:** 3 bare `except: pass` blocks in loop.py silently swallowed all exceptions.
**Fix:** All 3 replaced with `except Exception as e: logger.error(...)` including URL/query in message.

**Blocks fixed:**
1. `fill_data_gaps` search loop (line ~54) — logs: `[FAIL] Search query failed: {q}: {e}`
2. `execute_section_cycle` search loop (line ~107) — logs: `[FAIL] Search query failed: {q}: {e}`
3. `execute_section_cycle` ingestion loop (line ~127) — logs: `[FAIL] Ingestion failed for {url}: {e}`

**Note:** `fill_data_gaps` URL ingestion loop already had `except Exception as e: logger.error(...)` — not modified.

**Grep checks:**
```
grep -c "except: pass" src/research/archivist/loop.py               -> 0  PASS
grep -c "except Exception as e" src/research/archivist/loop.py      -> 4  PASS (>= 4)
grep -c "logger.error" src/research/archivist/loop.py               -> 4  PASS (>= 4)
```

---

## O5: False Rejection of .gov Pages

**Finding:** NIH page extracted to 78 chars — below 300-char length gate — due to overly aggressive heuristics.
**Fix:** Two targeted changes in `extract_text`:

1. Per-line minimum lowered from 20 to 10 chars: `len(chunk) > 10`
2. skip_rest gated on accumulated content: only activates when `len('\n'.join(filtered_lines)) < 500`

**Rationale:** Structured .gov pages have short label lines (rejected by old 20-char filter) and early navigation keywords in DOM (triggered skip_rest too early). With 500-char gate, skip_rest only activates when we're genuinely in header/nav zone without substantial body content.

**Grep checks:**
```
grep "len(chunk) > 10" src/research/archivist/crawler.py            -> MATCH  PASS
grep "len(chunk) > 20" src/research/archivist/crawler.py            -> NO MATCH  PASS
grep "500" src/research/archivist/crawler.py (filtered_lines)       -> MATCH  PASS
```

---

## Test Results

### tests/test_archivist_resilience.py (New — 20 tests)

```
PASSED  TestRetryClassification::test_backoff_called_between_retries
PASSED  TestRetryClassification::test_no_retry_on_http_403
PASSED  TestRetryClassification::test_no_retry_on_http_404
PASSED  TestRetryClassification::test_retries_on_connection_error_succeeds_second_attempt
PASSED  TestRetryClassification::test_retries_on_http_500_succeeds_third_attempt
PASSED  TestRetryClassification::test_retries_on_http_502
PASSED  TestRetryClassification::test_retries_on_timeout_succeeds_second_attempt
PASSED  TestRetryClassification::test_returns_none_after_all_three_500s
PASSED  TestLoopErrorLogging::test_execute_section_cycle_continues_after_error
PASSED  TestLoopErrorLogging::test_execute_section_cycle_logs_fetch_error
PASSED  TestLoopErrorLogging::test_fill_data_gaps_logs_fetch_error
PASSED  TestLoopErrorLogging::test_fill_data_gaps_search_error_logged
PASSED  TestExtractTextHeuristics::test_gov_html_extracts_over_300_chars
PASSED  TestExtractTextHeuristics::test_line_11_chars_is_kept
PASSED  TestExtractTextHeuristics::test_line_9_chars_is_dropped
PASSED  TestExtractTextHeuristics::test_skip_rest_activates_when_content_below_500
PASSED  TestExtractTextHeuristics::test_skip_rest_boundary_499_chars
PASSED  TestExtractTextHeuristics::test_skip_rest_does_not_activate_with_501_chars
PASSED  TestExtractTextHeuristics::test_threshold_boundary_exactly_10_chars_dropped
PASSED  TestExtractTextHeuristics::test_threshold_boundary_exactly_11_chars_kept

20/20 PASS
```

### Pre-existing tests (tests/test_atom_dedup.py — 6 tests)

```
6/6 PASS — no regressions
```

### Note on tests/validation/*.py

Pre-existing import errors (unrelated to this phase):
- `v01-v11`: `SheppardStorageAdapter` import error
- `v12`: `src.research.acquisition` module not found

These failures predate Phase 08.2 and are out of scope.

---

## Regression Assessment

No regressions introduced. Changes are scoped to:
- `src/research/archivist/crawler.py` — retry loop and extract_text heuristics
- `src/research/archivist/loop.py` — exception handling in 3 catch blocks

No schema changes, no new dependencies, no API surface changes.

---

## Verdict: PASS

All three soak findings (O1, O2, O5) are closed with automated test coverage.
