---
phase: 08.2-resilience-hardening
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/research/archivist/crawler.py
  - src/research/archivist/loop.py
  - tests/test_archivist_resilience.py
autonomous: true
requirements: [O1, O2, O3]
must_haves:
  truths:
    - "HTTP 5xx errors are retried up to 3 times before failing"
    - "HTTP 4xx errors fail immediately with no retry"
    - "Network errors (ConnectionError, Timeout) are retried up to 3 times"
    - "All fetch/ingest failures in loop.py are logged with URL and error detail"
    - "No bare except:pass remains in loop.py"
    - "NIH .gov page extracts more than 300 chars (passes length gate)"
  artifacts:
    - path: "src/research/archivist/crawler.py"
      provides: "Retry logic with 5xx/4xx classification, relaxed extraction heuristics"
      contains: "for attempt in range"
    - path: "src/research/archivist/loop.py"
      provides: "Explicit error logging on all catch blocks"
      contains: "logger.error"
    - path: "tests/test_archivist_resilience.py"
      provides: "Regression tests for O1, O2, O3 fixes"
      min_lines: 50
  key_links:
    - from: "src/research/archivist/crawler.py"
      to: "requests.get"
      via: "retry loop wrapping fetch_url fallback"
      pattern: "for attempt in range"
    - from: "src/research/archivist/loop.py"
      to: "logger.error"
      via: "except Exception as e blocks"
      pattern: "logger\\.error.*FAIL"
---

<objective>
Fix exactly three soak-identified issues in the archivist ingestion path:
1. HTTP 5xx gets zero retries (should get 3 attempts like network errors)
2. loop.py silently swallows all exceptions with bare `except: pass`
3. extract_text falsely rejects structured .gov pages (NIH page: 78 chars)

Purpose: Close the three gaps found in SOAK-RESULTS.md so the ingestion pipeline has bounded retries, visible failures, and fewer false rejections.
Output: Two modified source files + one test file proving the fixes work.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/gauntlet_phases/SOAK-RESULTS.md
@.planning/gauntlet_phases/phase08.1_critical_repairs/PHASE-08.1-VERIFICATION.md
@src/research/archivist/crawler.py
@src/research/archivist/loop.py
@src/research/archivist/config.py
@src/research/archivist/chunker.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: O1 -- Add retry classification to fetch_url in crawler.py</name>
  <files>src/research/archivist/crawler.py, tests/test_archivist_resilience.py</files>
  <read_first>
    - src/research/archivist/crawler.py (entire file, 116 lines)
    - src/research/archivist/config.py (for USER_AGENT import)
  </read_first>
  <behavior>
    - Test: fetch_url retries on HTTP 500 (mock requests.get to return 500 twice then 200 with HTML body) -- should succeed on 3rd attempt
    - Test: fetch_url retries on HTTP 502 -- same as 500
    - Test: fetch_url does NOT retry on HTTP 404 -- returns None after single attempt
    - Test: fetch_url does NOT retry on HTTP 403 -- returns None after single attempt
    - Test: fetch_url retries on ConnectionError -- succeeds on 2nd attempt
    - Test: fetch_url retries on Timeout -- succeeds on 2nd attempt
    - Test: fetch_url returns None after 3 failed attempts (all 500s) -- bounded, no infinite loop
  </behavior>
  <action>
**Current code (crawler.py lines 60-81):**
The fallback fetch block is a flat try/except with no retry:
```python
    try:
        response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        # ... PDF check, extract_text ...
    except Exception as e:
        return None
```

**Required change:** Replace the flat try/except block (lines 60-81) with a retry loop that classifies errors. The new code for the "Fallback to manual requests" section should be:

```python
    import time as _time

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            response.raise_for_status()

            # Check if it's a PDF
            content_type = response.headers.get('Content-Type', '').lower()
            if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
                try:
                    pdf_file = io.BytesIO(response.content)
                    reader = pypdf.PdfReader(pdf_file)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                    return text
                except Exception as pdf_err:
                    print(f"Error parsing PDF {url}: {pdf_err}")
                    return None

            return extract_text(response.text)

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 0
            if 500 <= status_code < 600 and attempt < max_retries - 1:
                _time.sleep(1 * (attempt + 1))  # Linear backoff: 1s, 2s
                continue
            # 4xx or final 5xx attempt -- not retryable / exhausted
            return None

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < max_retries - 1:
                _time.sleep(1 * (attempt + 1))
                continue
            return None

        except Exception as e:
            # Unexpected error -- do not retry
            return None

    return None
```

Move `import time as _time` to the top of the file with other imports (rename to avoid conflicts -- or just use `import time` at module level if no conflict exists). Check: the file does not currently import `time`, so `import time` at the top level is fine.

**Test file:** Create `tests/test_archivist_resilience.py`. Use `unittest.mock.patch` to mock `requests.get`. For 5xx tests, create a mock response with `.status_code = 500` and `.raise_for_status()` that raises `requests.exceptions.HTTPError(response=mock_response)`. For 4xx, same pattern with 404. For ConnectionError/Timeout, make `requests.get` raise those directly. Count call count to verify retry behavior.

**IMPORTANT:** The Firecrawl and BrowserManager blocks (lines 17-49) must be preserved exactly as-is above the retry loop. Only the "Fallback to manual requests" section changes.
  </action>
  <verify>
    <automated>cd /home/bamn/Sheppard && python -m pytest tests/test_archivist_resilience.py -v -k "retry or classification" --no-header 2>&1 | tail -20</automated>
  </verify>
  <acceptance_criteria>
    - grep -c "for attempt in range" src/research/archivist/crawler.py returns 1
    - grep -c "HTTPError" src/research/archivist/crawler.py returns at least 1
    - grep "500 <= status_code < 600" src/research/archivist/crawler.py succeeds
    - grep "ConnectionError.*Timeout" src/research/archivist/crawler.py succeeds
    - All retry/classification tests pass
    - No "except: pass" exists in crawler.py (grep -c "except: pass" returns 0 or is absent)
  </acceptance_criteria>
  <done>
    HTTP 5xx triggers retry (up to 3 attempts with backoff). HTTP 4xx returns None immediately. ConnectionError/Timeout retry. All bounded. Tests prove it.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: O2 -- Replace bare except:pass in loop.py with logged exceptions</name>
  <files>src/research/archivist/loop.py, tests/test_archivist_resilience.py</files>
  <read_first>
    - src/research/archivist/loop.py (entire file, 274 lines)
  </read_first>
  <behavior>
    - Test: When crawler.fetch_url raises inside execute_section_cycle's URL ingestion loop, the error is logged (check logger.error was called with URL in message)
    - Test: When search.search_web raises inside execute_section_cycle, the error is logged
    - Test: When crawler.fetch_url raises inside fill_data_gaps's URL ingestion loop, the error is logged
    - Test: After a logged error, the loop continues to process the next URL (not aborted)
  </behavior>
  <action>
**There are exactly 3 bare `except: pass` blocks to fix:**

**1. Line 54 in `fill_data_gaps` (search loop):**
```python
# BEFORE (line 53-54):
        except: pass

# AFTER:
        except Exception as e:
            logger.error(f"[FAIL] Search query failed: {q}: {e}")
```

**2. Line 107 in `execute_section_cycle` (search loop):**
```python
# BEFORE (line 106-107):
        except: pass

# AFTER:
        except Exception as e:
            logger.error(f"[FAIL] Search query failed: {q}: {e}")
```

**3. Line 127 in `execute_section_cycle` (URL ingestion loop):**
```python
# BEFORE (line 126-127):
        except: pass

# AFTER:
        except Exception as e:
            logger.error(f"[FAIL] Ingestion failed for {url}: {e}")
```

**Note:** The `fill_data_gaps` URL ingestion loop at line 74 already has `except Exception as e: logger.error(f"[FAIL] {url}: {e}")` -- this one is already correct, do not change it.

**Each replacement must:**
- Catch `Exception` (not bare `except`) to avoid catching SystemExit/KeyboardInterrupt
- Log via `logger.error` (logger is already imported and configured at module top)
- Include the URL or query string in the message for diagnosis
- NOT re-raise (the loop must continue to the next item)

**Tests:** Add tests to `tests/test_archivist_resilience.py` that mock `crawler.fetch_url` to raise RuntimeError, then call `execute_section_cycle` and `fill_data_gaps` with a minimal ResearchState. Assert `logger.error` was called. Also assert the function completes (returns, doesn't crash).

For test setup, create a minimal ResearchState:
```python
state = loop.ResearchState("test objective")
state.plan = [{"title": "Test Section", "goal": "test goal"}]
```
Mock all external calls (search.search_web, crawler.fetch_url, embeddings.*, retriever.*, synth.*, index.*) to isolate the error-handling behavior.
  </action>
  <verify>
    <automated>cd /home/bamn/Sheppard && python -m pytest tests/test_archivist_resilience.py -v -k "silent or logging or bare_except" --no-header 2>&1 | tail -20</automated>
  </verify>
  <acceptance_criteria>
    - grep -c "except: pass" src/research/archivist/loop.py returns 0
    - grep -c "except Exception as e" src/research/archivist/loop.py returns at least 4 (the 3 fixed + 1 already correct)
    - grep -c "logger.error" src/research/archivist/loop.py returns at least 4
    - All logging tests pass
  </acceptance_criteria>
  <done>
    Zero bare `except: pass` in loop.py. All three catch blocks log URL/query + error via logger.error. Loop continues after errors. Tests prove it.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: O3 -- Relax extract_text heuristics to reduce false rejection</name>
  <files>src/research/archivist/crawler.py, tests/test_archivist_resilience.py</files>
  <read_first>
    - src/research/archivist/crawler.py (lines 83-115 specifically -- the extract_text function)
  </read_first>
  <behavior>
    - Test: A line with 11 chars (e.g., "Short line.") is kept (was dropped by > 20 filter)
    - Test: A line with 9 chars is still dropped (below new 10-char threshold)
    - Test: Content after navigation keywords is kept when substantial content (>500 chars) already accumulated
    - Test: Content after navigation keywords is still dropped when little content (<100 chars) accumulated
    - Test: A representative structured .gov HTML snippet (with short label lines and navigation divs) extracts to > 300 chars
  </behavior>
  <action>
**Two targeted changes in `extract_text` (crawler.py lines 83-115):**

**Change 1: Lower per-line minimum from 20 to 10 chars (line 100):**
```python
# BEFORE (line 100):
    cleaned_text = '\n'.join(chunk for chunk in chunks if len(chunk) > 20)

# AFTER:
    cleaned_text = '\n'.join(chunk for chunk in chunks if len(chunk) > 10)
```

**Change 2: Don't skip_rest if substantial content already accumulated (lines 105-109):**
```python
# BEFORE (lines 105-109):
    filtered_lines = []
    skip_rest = False
    for line in cleaned_text.split('\n'):
        l_lower = line.lower()
        if any(j in l_lower for j in ["related topics", "most read", "editors' picks", "footer", "sidebar", "navigation"]):
            skip_rest = True
        if skip_rest: continue

# AFTER:
    filtered_lines = []
    skip_rest = False
    for line in cleaned_text.split('\n'):
        l_lower = line.lower()
        if any(j in l_lower for j in ["related topics", "most read", "editors' picks", "footer", "sidebar", "navigation"]):
            if len('\n'.join(filtered_lines)) < 500:
                skip_rest = True
        if skip_rest: continue
```

This means: if we already have 500+ chars of accumulated content when we hit a navigation cue, we do NOT activate skip_rest. The rationale is that on structured pages (like NIH), navigation keywords appear early in the DOM but real content follows. The 500-char threshold ensures we only skip tail content when we genuinely haven't found the main body yet (i.e., we're still in the header/nav zone).

**No other changes to extract_text.** The junk_lines filter (lines 111-113) and the rest of the function remain unchanged.

**Tests:** Add tests to `tests/test_archivist_resilience.py`:
- Test the `> 10` threshold with crafted lines
- Test the skip_rest gating with a mock HTML page that has "navigation" early but real content after
- Test with a minimal .gov-like HTML structure that previously would have been stripped to < 300 chars
  </action>
  <verify>
    <automated>cd /home/bamn/Sheppard && python -m pytest tests/test_archivist_resilience.py -v -k "extract or false_reject or gov" --no-header 2>&1 | tail -20</automated>
  </verify>
  <acceptance_criteria>
    - grep "len(chunk) > 10" src/research/archivist/crawler.py succeeds
    - grep "len(chunk) > 20" src/research/archivist/crawler.py fails (old threshold gone)
    - grep "500" src/research/archivist/crawler.py finds the accumulated-content threshold
    - All extraction tests pass
  </acceptance_criteria>
  <done>
    Per-line minimum lowered from 20 to 10 chars. skip_rest only activates when less than 500 chars accumulated. Structured .gov pages with short label lines no longer falsely rejected. Tests prove it.
  </done>
</task>

<task type="auto">
  <name>Task 4: Verification -- Run full acceptance criteria and produce evidence</name>
  <files>tests/test_archivist_resilience.py</files>
  <read_first>
    - tests/test_archivist_resilience.py (the file created by Tasks 1-3)
    - src/research/archivist/crawler.py (verify changes applied)
    - src/research/archivist/loop.py (verify changes applied)
  </read_first>
  <action>
Run all tests and all grep-based acceptance criteria from Tasks 1-3. Collect results.

**Step 1:** Run the full test suite:
```bash
cd /home/bamn/Sheppard && python -m pytest tests/test_archivist_resilience.py -v --tb=short 2>&1
```

**Step 2:** Run grep checks:
```bash
# O1 checks
grep -c "for attempt in range" src/research/archivist/crawler.py   # expect: 1
grep -c "HTTPError" src/research/archivist/crawler.py               # expect: >= 1
grep "500 <= status_code < 600" src/research/archivist/crawler.py   # expect: match

# O2 checks
grep -c "except: pass" src/research/archivist/loop.py               # expect: 0
grep -c "except Exception as e" src/research/archivist/loop.py      # expect: >= 4
grep -c "logger.error" src/research/archivist/loop.py               # expect: >= 4

# O3 checks
grep "len(chunk) > 10" src/research/archivist/crawler.py            # expect: match
grep "len(chunk) > 20" src/research/archivist/crawler.py            # expect: NO match
```

**Step 3:** Also run existing Phase 08.1 regression tests to confirm no regressions:
```bash
cd /home/bamn/Sheppard && python -m pytest tests/test_chunking_validation.py -v --tb=short 2>&1
```

If any check fails, fix the issue in the relevant source file before proceeding.

**Step 4:** Summarize results in the plan summary.
  </action>
  <verify>
    <automated>cd /home/bamn/Sheppard && python -m pytest tests/test_archivist_resilience.py tests/test_chunking_validation.py -v --tb=short 2>&1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - All tests in test_archivist_resilience.py pass
    - All tests in test_chunking_validation.py pass (no regression)
    - All grep checks from Tasks 1-3 return expected values
  </acceptance_criteria>
  <done>
    All O1/O2/O3 fixes verified by automated tests and grep checks. No regressions in Phase 08.1 test suite. Phase 08.2 implementation complete.
  </done>
</task>

</tasks>

<verification>
All three soak findings closed:

1. **O1 (Retry classification):** `fetch_url` has a `for attempt in range(3)` loop. HTTP 5xx retries with backoff. HTTP 4xx returns None immediately. ConnectionError/Timeout retry. Bounded -- max 3 attempts.

2. **O2 (Silent failure):** Zero `except: pass` in loop.py. All catch blocks use `except Exception as e: logger.error(...)` with URL/query in message. Loop continues after error.

3. **O3 (False rejection):** Per-line minimum lowered to 10 chars. skip_rest gated on accumulated content (500 chars). Structured .gov pages extract properly.

No scope creep: only crawler.py, loop.py, and test file touched. No new frameworks, no circuit breakers, no system-wide changes.
</verification>

<success_criteria>
- pytest tests/test_archivist_resilience.py: all pass
- pytest tests/test_chunking_validation.py: all pass (no regression)
- grep -c "except: pass" src/research/archivist/loop.py == 0
- grep -c "for attempt in range" src/research/archivist/crawler.py == 1
- grep "len(chunk) > 10" src/research/archivist/crawler.py matches
- grep "len(chunk) > 20" src/research/archivist/crawler.py does NOT match
</success_criteria>

<output>
After completion, create `.planning/gauntlet_phases/phase08.2_resilience_hardening/08.2-01-SUMMARY.md`
</output>
