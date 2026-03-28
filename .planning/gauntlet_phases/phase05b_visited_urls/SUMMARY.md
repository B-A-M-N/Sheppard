---
phase: 05b-visited-urls
plan: 01
subsystem: research/acquisition + memory
tags: [dedup, frontier, persistence, visited-urls, restart]
dependency_graph:
  requires: []
  provides: [get_visited_urls, visited-url-persistence]
  affects: [AdaptiveFrontier._load_checkpoint, CorpusStore, SheppardStorageAdapter]
tech_stack:
  added: []
  patterns: [protocol-stub + concrete-impl, set-comprehension from DB rows]
key_files:
  modified:
    - src/memory/storage_adapter.py
    - src/research/acquisition/frontier.py
decisions:
  - "Use list_sources as the underlying query for get_visited_urls — no new DB query needed"
  - "Return set[str] (builtin) rather than Set[str] (typing) for Python 3.10+ style"
metrics:
  duration: ~5m
  completed: 2026-03-27
  tasks_completed: 2
  files_modified: 2
---

# Phase 05b Plan 01: Visited URL Persistence Summary

**One-liner:** Wired `get_visited_urls(mission_id)` from `corpus.sources` into `_load_checkpoint` to restore the dedup set on every AdaptiveFrontier restart, closing gap A10.

---

## What Changed

### Task 1 — `src/memory/storage_adapter.py`

Added `get_visited_urls` in two places:

1. **CorpusStore protocol** (line 92): protocol stub declaring the contract.
   ```python
   async def get_visited_urls(self, mission_id: str) -> set[str]: ...
   ```

2. **SheppardStorageAdapter** (line 532): concrete implementation that delegates to the existing `list_sources` method and extracts the `normalized_url` field from each row.
   ```python
   async def get_visited_urls(self, mission_id: str) -> set[str]:
       rows = await self.list_sources(mission_id)
       return {r["normalized_url"] for r in rows if r.get("normalized_url")}
   ```

### Task 2 — `src/research/acquisition/frontier.py`

In `_load_checkpoint`, replaced two dead-comment FIXME lines with:
```python
self.visited_urls = await self.sm.adapter.get_visited_urls(self.mission_id)
```

Added a parallel log line after the nodes log:
```python
if self.visited_urls:
    console.print(f"[dim]  - Pre-loaded {len(self.visited_urls)} visited URLs from DB.[/dim]")
```

---

## Why

**Gap A10:** `AdaptiveFrontier.visited_urls` was initialized to `set()` on every startup. All previously fetched URLs stored in `corpus.sources.normalized_url` were ignored, allowing the frontier to re-enqueue and re-fetch URLs that were already ingested in a prior run.

The fix uses the already-populated `corpus.sources` table as the source of truth — no schema change required.

---

## Verification Evidence

```
# AST + occurrence check
PASS: get_visited_urls present in both CorpusStore and SheppardStorageAdapter

# FIXME removal + AST parse check
PASS: frontier.py parses cleanly and FIXME block is replaced

# Import checks
adapter OK
frontier OK

# Grep: storage_adapter.py
92:    async def get_visited_urls(self, mission_id: str) -> set[str]: ...
532:    async def get_visited_urls(self, mission_id: str) -> set[str]:

# Grep: frontier.py
150:        self.visited_urls = await self.sm.adapter.get_visited_urls(self.mission_id)

# FIXME count in frontier.py
0

# Implementation body (get_visited_urls in SheppardStorageAdapter)
    async def get_visited_urls(self, mission_id: str) -> set[str]:
        rows = await self.list_sources(mission_id)
        return {r["normalized_url"] for r in rows if r.get("normalized_url")}
```

All acceptance criteria met:
- `get_visited_urls` appears in CorpusStore (protocol stub) and SheppardStorageAdapter (concrete impl)
- Implementation body contains `list_sources` and `normalized_url`
- `_load_checkpoint` assigns `self.visited_urls` from the method
- No FIXME comment remains in frontier.py
- Both files import cleanly

---

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1    | 59e86a2 | feat(05b-01): add get_visited_urls to CorpusStore protocol and SheppardStorageAdapter |
| 2    | 0cb3811 | feat(05b-02): wire _load_checkpoint to restore visited_urls from DB on restart |

---

## Deviations from Plan

None - plan executed exactly as written.

---

## Status: PASS

## Self-Check: PASSED

- `src/memory/storage_adapter.py` — FOUND, contains 2 occurrences of `get_visited_urls`
- `src/research/acquisition/frontier.py` — FOUND, contains 1 occurrence of `get_visited_urls`, FIXME count = 0
- Commits 59e86a2 and 0cb3811 — FOUND in git log
