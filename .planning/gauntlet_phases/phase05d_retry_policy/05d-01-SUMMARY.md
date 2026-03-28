---
phase: 05d-retry-policy
plan: "01"
subsystem: core/system.py — _vampire_loop exception handler
tags: [retry, dead-letter, job-queue, vampire-loop, gap-closure]
requirements: [RETRY-01, RETRY-02]

dependency_graph:
  requires: []
  provides:
    - "Job retry logic with exponential backoff (up to 3 attempts) in _vampire_loop"
    - "Dead-letter terminal log ([DEAD] prefix) for jobs exhausting retry cap"
    - "Pipeline-wide retry policy inventory comment block in system.py"
  affects:
    - "queue:scraping Redis queue (jobs are re-enqueued on retry)"
    - "Logging output (warning on retry, error on dead-letter)"

tech_stack:
  added:
    - "bare import aiohttp (top-level, line 37) — enables aiohttp.ClientError reference in handler"
  patterns:
    - "retry_count field on job dict (default 0 if absent — backward compatible)"
    - "Exponential backoff: 2^retry_count seconds (1s, 2s, 4s)"
    - "_retryable flag for log text variation only; gate is purely retry_count < 3"

key_files:
  modified:
    - path: "src/core/system.py"
      changes:
        - "Line 37: added bare top-level `import aiohttp`"
        - "Lines 305-337: inserted RETRY POLICY INVENTORY comment block (3 layers)"
        - "Lines 388-416: replaced 2-line bare except with 27-line retry-aware handler"

decisions:
  - "All exceptions retry up to the cap (not just transient ones). _retryable only varies log text."
  - "Backoff formula is 2^retry_count: attempt 0->1s, 1->2s, 2->4s — matches crawler._scrape_with_retry base pattern."
  - "When _job is empty (dequeue itself failed), we fall through to [DEAD] immediately — no point re-enqueueing an unknown job."
  - "Budget-hold re-enqueue (line 362) is explicitly excluded from retry_count: it is a hold, not a failure."

metrics:
  duration: "~5 minutes"
  completed_date: "2026-03-27"
  tasks_completed: 2
  files_modified: 1
---

# Phase 05d Plan 01: Job Retry Logic and Retry Policy Inventory Summary

One-liner: Replaced silent exception drop in vampire loop with 3-attempt exponential-backoff retry, [DEAD] dead-letter logging, and a pipeline-wide retry inventory comment block.

## What Changed

### src/core/system.py — line 37
Added bare top-level `import aiohttp` so that `aiohttp.ClientError` resolves correctly in the exception handler at runtime.

### src/core/system.py — lines 305-337 (Task 2)
Inserted a 33-line `RETRY POLICY INVENTORY` comment block immediately before `async def _vampire_loop`. Documents all three pipeline retry layers:
- Layer 1: Fetch (crawler._scrape_with_retry) — 3 attempts, exponential backoff, returns None on terminal.
- Layer 2: Distillation (pipeline.py) — 1 attempt, source marked "error" on failure, batch continues.
- Layer 3: Job (this loop) — 3 attempts via retry_count field, exponential backoff, dead-lettered at cap.

### src/core/system.py — lines 388-416 (Task 1)
Replaced the original 2-line bare except:
```python
except Exception as e:
    logger.error(f"[Vampire-{vampire_id}] Indigestion on ...")
    await asyncio.sleep(2)
```
With a 27-line retry-aware handler:
- Resolves `_job`, `_url`, `_retry` safely (handles dequeue failure case).
- Classifies exception type into `_retryable` (used for log text only).
- If `_job and _retry < 3`: increments retry_count, sleeps `2^retry` seconds, re-enqueues.
- Else (cap reached or no job): logs `[DEAD]` terminal error, does NOT re-enqueue.

## Retry Policy Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Retry gate condition | `retry_count < 3` (cap = 3 attempts) | Matches Layer 1 (crawler) cap; consistent across pipeline |
| Retryable exception scope | All exceptions retry up to cap | Simpler; avoids silent drops on unexpected error types |
| _retryable flag | Log text variation only | Distinguishes transient vs unexpected in logs without changing gate logic |
| Backoff formula | `2 ** retry_count` seconds | 1s/2s/4s — mirrors crawler._scrape_with_retry base pattern |
| Empty job handling | Falls through to [DEAD] path | No job means nothing to re-enqueue; avoids infinite loop on dequeue failure |
| Budget-hold exclusion | Re-enqueue without touching retry_count | Hold is not a failure; must not consume retry budget |

## Verification Evidence

```
=== Task 1 checks ===
37:import aiohttp                        (bare top-level import — 1 line)
329:    #   Attempts:   3 (job["retry_count"] field, default 0).
330:    #   Backoff:    Exponential — delay = 2^retry_count seconds (1s, 2s, 4s).
331:    #   Retryable:  All exceptions retry up to the cap (retry_count < 3).
334:    #   Non-retryable / Terminal: retry_count >= 3 → ...
336:    #               (not counted against retry_count — ...)
392:                _retry = _job.get("retry_count", 0)   (read)
403:                    _job["retry_count"] = _retry + 1   (increment)
414:                        f"[DEAD] [Vampire-{vampire_id}] ...  (terminal log — 1 line)
408:                        f"... Requeueing in {_backoff}s."  (retry log — 1 line)
411:                    await self.adapter.enqueue_job("queue:scraping", _job)  (re-enqueue)

=== Task 2 checks ===
306:    # RETRY POLICY INVENTORY — Pipeline-Wide Summary   (exactly 1 line)
309:    # Layer 1 — Fetch (crawler._scrape_with_retry):
318:    # Layer 2 — Distillation (pipeline.py per-source try/except):
327:    # Layer 3 — Job (this loop, _vampire_loop):

=== Syntax ===
syntax OK
```

All acceptance criteria from both tasks confirmed passing.

## Deviations from Plan

None — plan executed exactly as written. The only implicit action was adding `import aiohttp` (Step 0 of Task 1 spec) since it was absent; the plan explicitly required this check.

## Known Stubs

None. All logic is fully wired.

## Self-Check: PASSED

- `/home/bamn/Sheppard/src/core/system.py` modified and verified present.
- `grep "^import aiohttp"` returns 1 line at line 37.
- `grep "retry_count"` returns lines in comment block (329-336) and in handler (392, 403).
- `grep "\[DEAD\]"` returns exactly 1 line (414) — in the handler, not introduced by the comment block.
- `grep "RETRY POLICY INVENTORY"` returns exactly 1 line (306).
- `python -c "import ast; ast.parse(...)"` printed "syntax OK".
- Commits pending (Bash commit was blocked; changes staged in working tree).
