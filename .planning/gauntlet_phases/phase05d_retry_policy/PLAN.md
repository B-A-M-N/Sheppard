---
phase: 05d-retry-policy
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/core/system.py
autonomous: true
requirements: [RETRY-01, RETRY-02]
gap_closure: true

must_haves:
  truths:
    - "A job that raises a transient exception is re-enqueued with retry_count incremented, not silently dropped"
    - "A job that has failed 3 times is logged with [DEAD] prefix and is NOT re-enqueued"
    - "Network/timeout exceptions are classified retryable; all other exceptions are treated as retryable up to the retry cap"
    - "Every retry attempt emits a log line with the current attempt number and exception"
    - "The full pipeline retry inventory is documented in a comment block at the top of the vampire section"
  artifacts:
    - path: "src/core/system.py"
      provides: "Job retry logic in _vampire_loop plus retry policy comment block"
      contains: "retry_count"
    - path: "src/core/system.py"
      provides: "Dead-letter terminal log"
      contains: "[DEAD]"
    - path: "src/core/system.py"
      provides: "Retry policy inventory comment"
      contains: "RETRY POLICY INVENTORY"
  key_links:
    - from: "_vampire_loop exception handler"
      to: "queue:scraping Redis queue"
      via: "adapter.enqueue_job with incremented retry_count"
      pattern: "retry_count.*<.*3"
    - from: "_vampire_loop exception handler"
      to: "logger.error"
      via: "terminal failure log with [DEAD] prefix"
      pattern: "\\[DEAD\\]"
---

<objective>
Close gap A12: the vampire loop silently drops jobs on exception. This plan adds explicit retry logic (retry_count field, re-enqueue on transient failures, dead-letter log on terminal failure) and documents all retry policies in the pipeline in a comment block.

Purpose: Jobs that fail due to transient network or service conditions should retry predictably. Jobs that repeatedly fail should be surfaced clearly, not vanish.
Output: Modified src/core/system.py with retry-aware exception handler and retry policy inventory comment.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/gauntlet_phases/phase05d_retry_policy/PHASE-05D-PLAN.md

<!-- Key interfaces the executor needs. Extracted from codebase. -->
<interfaces>
From src/core/system.py — _vampire_loop (lines 304-356):

The loop dequeues a dict `job` from "queue:scraping" via:
    job = await self.adapter.dequeue_job("queue:scraping", timeout_s=10)

Job dict shape (set by crawler.py discover_and_enqueue and _offload_to_slow_lane):
    {
        "topic_id": str,
        "mission_id": str,
        "url": str,
        "url_hash": str,          # md5 of url, may be absent
        "lane": "fast" | "slow",  # may be absent
        "priority": int,          # may be absent
        "requires_js": bool,      # may be absent
        # NEW field to add:
        "retry_count": int        # default 0 when absent
    }

Re-enqueue via:
    await self.adapter.enqueue_job("queue:scraping", job)

Current bare except (lines 354-356) — the target to replace:
    except Exception as e:
        logger.error(f"[Vampire-{vampire_id}] Indigestion on {job.get('url') if 'job' in locals() else 'unknown'}: {e}")
        await asyncio.sleep(2)

From src/research/acquisition/crawler.py — _scrape_with_retry (lines 335-359):
    max_retries = config.max_retries  # default 3
    retry_base_delay = config.retry_base_delay  # default 1.0 seconds
    # Per attempt: asyncio.sleep(retry_base_delay * (2 ** attempt))
    # Returns None on all-attempts exhausted — does NOT raise

From src/research/condensation/pipeline.py (lines 82-128):
    # Per-source try/except; on exception: marks source status="error" and continues batch
    except Exception as e:
        logger.error(f"[Distillery] Smelting failed for {source_id}: {e}")
        await self.adapter.pg.update_row("corpus.sources", "source_id",
            {"source_id": source_id, "status": "error"})
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add job retry logic to vampire loop</name>
  <files>src/core/system.py</files>
  <read_first>
    - src/core/system.py lines 304-356 (full _vampire_loop method)
    - src/core/system.py lines 1-50 (imports — confirm asyncio and aiohttp are already imported)
  </read_first>
  <action>
Replace the bare `except Exception` block in `_vampire_loop` (lines 354-356) with retry-aware logic. The change is surgical — only the exception handler block is modified.

**Step 0 — Ensure aiohttp is directly imported:**
Run `grep -n "^import aiohttp" src/core/system.py`. If that returns nothing, add `import aiohttp` to the top-level import block near line 37-44 (alongside `import asyncpg`, `import redis.asyncio`, etc.). This must be a bare top-level `import aiohttp`, not an indented or inline import, because `aiohttp.ClientError` is referenced in the exception handler.

**Exact replacement:**

BEFORE (lines 354-356):
```python
            except Exception as e:
                logger.error(f"[Vampire-{vampire_id}] Indigestion on {job.get('url') if 'job' in locals() else 'unknown'}: {e}")
                await asyncio.sleep(2)
```

AFTER:
```python
            except Exception as e:
                # Resolve job reference safely (may not exist if dequeue itself failed)
                _job = job if 'job' in locals() and job else {}
                _url = _job.get("url", "unknown")
                _retry = _job.get("retry_count", 0)

                # Classify for log message only — all exceptions retry up to the cap.
                _retryable = isinstance(e, (
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    ConnectionError,
                    TimeoutError,
                ))

                if _job and _retry < 3:
                    _job["retry_count"] = _retry + 1
                    _backoff = 2 ** _retry  # 1s, 2s, 4s
                    _kind = "transient" if _retryable else "non-retryable type"
                    logger.warning(
                        f"[Vampire-{vampire_id}] {_kind.capitalize()} failure on {_url} "
                        f"(attempt {_retry + 1}/3): {e}. Requeueing in {_backoff}s."
                    )
                    await asyncio.sleep(_backoff)
                    await self.adapter.enqueue_job("queue:scraping", _job)
                else:
                    logger.error(
                        f"[DEAD] [Vampire-{vampire_id}] Terminal failure on {_url} "
                        f"after {_retry} attempt(s): {e}. Job dropped."
                    )
```

**Notes on the logic:**
- `retry_count` is read from the job dict; defaults to 0 if the field is absent (backward-compatible with jobs enqueued before this change).
- Backoff sequence: attempt 0 → 1s, attempt 1 → 2s, attempt 2 → 4s (matches crawler._scrape_with_retry base pattern).
- When `retry_count >= 3`, we log `[DEAD]` and do NOT call `enqueue_job` — the job is gone.
- `asyncio.CancelledError` is caught earlier in the existing handler (line 352) and is unaffected.
- `_retryable` is used only to vary the log message text ("transient" vs "non-retryable type"). The retry gate is purely `_retry < 3` — all exceptions retry up to the cap.
- The redundant inner `if _job:` guard before `enqueue_job` is removed; `_job` truthiness is already guaranteed by the outer `if _job and _retry < 3:` branch.
  </action>
  <verify>
    <automated>grep -n "^import aiohttp" /home/bamn/Sheppard/src/core/system.py && grep -n "retry_count" /home/bamn/Sheppard/src/core/system.py && grep -n "\[DEAD\]" /home/bamn/Sheppard/src/core/system.py && grep -n "Requeueing in" /home/bamn/Sheppard/src/core/system.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep "^import aiohttp" src/core/system.py` returns exactly 1 line (bare top-level import)
    - `grep "retry_count" src/core/system.py` returns at least 3 lines (read, increment, assign)
    - `grep "\[DEAD\]" src/core/system.py` returns exactly 1 line inside _vampire_loop
    - `grep "Requeueing in" src/core/system.py` returns exactly 1 line
    - `grep "enqueue_job.*scraping.*_job" src/core/system.py` returns at least 1 line (the re-enqueue call in the retry branch)
    - `python -c "import ast; ast.parse(open('src/core/system.py').read()); print('syntax OK')"` prints "syntax OK"
  </acceptance_criteria>
  <done>The vampire loop re-enqueues jobs with incremented retry_count on transient failures (up to 3 attempts with exponential backoff) and logs [DEAD] on terminal failure without re-enqueueing. Silent job drops are eliminated. aiohttp is directly imported so the ClientError reference resolves at runtime.</done>
</task>

<task type="auto">
  <name>Task 2: Add retry policy inventory comment block to system.py</name>
  <files>src/core/system.py</files>
  <read_first>
    - src/core/system.py lines 300-310 (section header comment above _vampire_loop — find exact insertion point)
    - src/research/acquisition/crawler.py lines 55-60 and 335-359 (CrawlerConfig.max_retries, _scrape_with_retry)
    - src/research/condensation/pipeline.py lines 126-129 (distillation per-source error handler)
  </read_first>
  <action>
Insert a comment block directly above the `_vampire_loop` method definition (above the `async def _vampire_loop` line) that documents the full retry inventory for the pipeline. This is a documentation-only change — no logic is altered.

**Insert this comment block immediately before `async def _vampire_loop(self, vampire_id: int):`:**

```python
    # ──────────────────────────────────────────────────────────────────────
    # RETRY POLICY INVENTORY — Pipeline-Wide Summary
    # ──────────────────────────────────────────────────────────────────────
    #
    # Layer 1 — Fetch (crawler._scrape_with_retry):
    #   Scope:      Per URL, fast-lane scrapes only.
    #   Attempts:   3 (CrawlerConfig.max_retries default).
    #   Backoff:    Exponential — delay = retry_base_delay * 2^attempt (1s, 2s, 4s).
    #   Trigger:    Any exception during aiohttp POST to firecrawl-local.
    #   Terminal:   Returns None after 3 failures; caller receives None and skips ingestion.
    #   Non-retryable: HTTP non-200 and empty markdown are treated as immediate None
    #                  (no retry on 4xx — firecrawl returns 200 on most errors).
    #
    # Layer 2 — Distillation (pipeline.py per-source try/except):
    #   Scope:      Per source in a condensation batch.
    #   Attempts:   1 (no retry — each source is processed once per batch run).
    #   Backoff:    N/A.
    #   Trigger:    Any exception during LLM extraction or atom storage.
    #   Terminal:   Source status set to "error" in corpus.sources; batch continues.
    #   Non-retryable: All failures are terminal at this layer (rely on job-level retry
    #                  to re-present the source in a future batch if needed).
    #
    # Layer 3 — Job (this loop, _vampire_loop):
    #   Scope:      Per job dequeued from queue:scraping.
    #   Attempts:   3 (job["retry_count"] field, default 0).
    #   Backoff:    Exponential — delay = 2^retry_count seconds (1s, 2s, 4s).
    #   Retryable:  All exceptions retry up to the cap (retry_count < 3).
    #               aiohttp.ClientError / asyncio.TimeoutError / ConnectionError /
    #               TimeoutError are additionally labelled "transient" in log output.
    #   Non-retryable / Terminal: retry_count >= 3 → dead-lettered (terminal log, NOT re-enqueued).
    #   Budget-hold: Jobs that exceed the crawl budget are re-enqueued unconditionally
    #               (not counted against retry_count — this is a hold, not a failure).
    # ──────────────────────────────────────────────────────────────────────
```

**Insertion point:** The comment goes inside the class body, at the same indentation level as the method definitions (4 spaces). It must appear immediately before the `async def _vampire_loop` line. There is already a section divider comment on line 300 (`# Internal Helpers`); place this new block after that divider and before the method definition.
  </action>
  <verify>
    <automated>grep -n "RETRY POLICY INVENTORY" /home/bamn/Sheppard/src/core/system.py && grep -n "Layer 1" /home/bamn/Sheppard/src/core/system.py && grep -n "Layer 3" /home/bamn/Sheppard/src/core/system.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep "RETRY POLICY INVENTORY" src/core/system.py` returns exactly 1 line
    - `grep "Layer 1" src/core/system.py` returns 1 line referencing crawler._scrape_with_retry
    - `grep "Layer 2" src/core/system.py` returns 1 line referencing pipeline.py distillation
    - `grep "Layer 3" src/core/system.py` returns 1 line referencing _vampire_loop
    - `grep "\[DEAD\]" src/core/system.py` still returns 1 line (from Task 1 — comment block must not introduce a second [DEAD] line; use description text instead)
    - `python -c "import ast; ast.parse(open('src/core/system.py').read()); print('syntax OK')"` prints "syntax OK"
  </acceptance_criteria>
  <done>A structured comment block above _vampire_loop enumerates all three retry layers (fetch, distillation, job), their attempt counts, backoff formulas, retryable exception types, and terminal behavior. A future reader can understand the full pipeline retry contract without reading multiple source files.</done>
</task>

</tasks>

<verification>
Run all acceptance criteria commands sequentially after both tasks complete:

```bash
cd /home/bamn/Sheppard

# Task 1 checks
grep -n "^import aiohttp" src/core/system.py
grep -n "retry_count" src/core/system.py
grep -n "\[DEAD\]" src/core/system.py
grep -n "Requeueing in" src/core/system.py
grep -n "enqueue_job" src/core/system.py

# Task 2 checks
grep -n "RETRY POLICY INVENTORY" src/core/system.py
grep -n "Layer 1\|Layer 2\|Layer 3" src/core/system.py

# Syntax check (must print "syntax OK")
python -c "import ast; ast.parse(open('src/core/system.py').read()); print('syntax OK')"
```

Expected final state of the exception handler in _vampire_loop: the bare two-line `except Exception` block is replaced with ~20 lines that read `retry_count`, gate on `_retry < 3`, re-enqueue with backoff if under the cap, and log `[DEAD]` if at cap. `_retryable` is present but used only to vary log text.
</verification>

<success_criteria>
- `grep "^import aiohttp" src/core/system.py` returns exactly 1 line (bare top-level import, not indirect)
- `[DEAD]` log line exists exactly once in _vampire_loop for the terminal failure branch
- `retry_count` field is read and incremented within the exception handler
- Jobs under the retry cap are re-enqueued via `adapter.enqueue_job` with `retry_count` incremented
- Retry condition is `if _job and _retry < 3:` — no dead boolean in the gate
- Retry policy inventory comment block covers all three pipeline layers with accurate detail
- `python -c "import ast; ast.parse(...)"` confirms no syntax errors introduced
- No existing behavior changed outside the exception handler block
</success_criteria>

<output>
After completion, create `.planning/gauntlet_phases/phase05d_retry_policy/05d-01-SUMMARY.md` with:
- What changed (exact lines modified in system.py)
- Retry policy decisions made (exception types classified as retryable, backoff formula, cap)
- Verification evidence (grep output confirming all acceptance criteria pass)
- Any deviations from the plan and why
</output>
