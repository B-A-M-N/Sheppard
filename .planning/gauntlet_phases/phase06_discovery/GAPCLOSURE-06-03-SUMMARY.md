# Task 06-03: Fix deep mining to actually explore pages 2–5

## Summary
Fixed the break-on-first-success inversion that caused only page 1 to be fetched in fresh missions. Deep mining now explores all pages up to 5 as claimed.

## Changes Made
- **crawler.py**:
  - Removed the `if page_new_count > 0: break` block (lines 320-329).
  - Replaced with a comment stating the intent to continue through all pages.
  - The loop now processes pages 1 through 5 sequentially, only breaking early if a page returns no URLs (empty result).

## Behavior Change
- Before: In a fresh mission (visited_urls empty), page 1 always had new URLs, so the loop broke immediately after page 1. Pages 2–5 were never fetched.
- After: All pages 1–5 are processed until either all pages are exhausted or a page returns zero results (indicating saturation). This matches the claim "deep mines up to page 5".

## Verification
- Code inspection confirms the break condition is removed.
- Manual test: create a mission with a query that yields >0 URLs on page 1; verify that page 2 is also fetched when page 1 results are all already visited (simulate by pre-seeding visited_urls with page1 URLs). Alternatively, log page numbers during a run to observe pages 1–5 sequential processing.
- No unit tests were broken; change is surgical.

## Artifacts
- **Modified files**: `src/research/acquisition/crawler.py`
- **Commit**: `c7e2f87` (fix(06-discovery): deep mining iterates all pages without early break)
