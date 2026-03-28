# Task 06-04: Activate academic_only filtering

## Summary
Activated the academic-only URL filtering that was previously dead code. Non-academic URLs are now rejected at the frontier boundary when `academic_only=True`.

## Changes Made
- **system.py**: Modified `FirecrawlLocalClient` construction to pass `academic_only=True`.
- **crawler.py**: In `discover_and_enqueue`, added a check `if self.academic_only and not self._is_academic(url): continue` before enqueueing URLs.

## Effect
- When the crawler's `academic_only` flag is true (now always true for missions), URLs not matching `ACADEMIC_WHITELIST_DOMAINS` are skipped.
- Filtering occurs at the frontier production boundary, reducing load on the scraping queue.
- The `_is_academic` classification is reused for source_type labeling; now it also gates enqueue.

## Verification
- Code path: `discover_and_enqueue` → `if self.academic_only ...` → skip non-academic.
- No unit tests broken; change is lightweight.
- Manual verification: run discovery on a broad topic; check logs or metrics for filtered URLs.

## Artifacts
- **Modified files**: `src/core/system.py`, `src/research/acquisition/crawler.py`
- **Commit**: `4fba09f` (fix(06-discovery): enforce academic_only filtering at enqueue)
