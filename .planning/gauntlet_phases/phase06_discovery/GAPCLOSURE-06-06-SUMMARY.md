# Task 06-06: Add queue backpressure mechanism

## Summary
Implemented a circuit-breaker style backpressure mechanism in the Redis queue adapter. When the queue depth reaches 10,000 jobs, further enqueues are rejected, and the frontier stops producing work until the queue drains.

## Changes Made
- **redis.py**:
  - Added `import logging` and `logger = logging.getLogger(__name__)`.
  - Introduced `MAX_QUEUE_DEPTH = 10000` constant.
  - Modified `enqueue_job` to:
    - Check current depth with `await self.client.llen(queue_name)`.
    - Reject with a warning log if depth >= limit (return `False`).
    - Return `True` on successful enqueue.
- **crawler.py**:
  - In `discover_and_enqueue`, added `backpressure_triggered` flag.
  - Changed enqueue call to capture `success` and only mark URL visited/increment counters on success.
  - On rejection, set `backpressure_triggered = True` and break out of the inner URL loop.
  - After inner loop, if `backpressure_triggered`, break outer page loop as well.

## Behavior
- Frontier workers (vampires) consume from the queue at a finite rate. When consumption falls behind production, queue depth grows.
- Once the depth hits the threshold, new URL discovery stops immediately, preventing unbounded growth.
- As workers finish jobs and pop from the queue, depth decreases; subsequent enqueue attempts can succeed, resuming production automatically.
- This is a minimal viable backpressure; more sophisticated pause/resume signaling can be added later.

## Verification
- Code inspection confirms `llen` check and return value handling.
- Logs: watch for warnings like "Queue depth X exceeds limit — rejecting job".
- Metrics: queue depth should plateau around the threshold under sustained load.

## Artifacts
- **Modified files**: `src/memory/adapters/redis.py`, `src/research/acquisition/crawler.py`
- **Commit**: `94bdfa8` (fix(06-discovery): add queue depth check to enqueue_job as circuit breaker)
