---
phase: 06-discovery
plan: 02
type: gap_closure
wave: 2
depends_on: ["06-01"]
files_modified: []
autonomous: true
requirements: [DISCOVERY-06, DISCOVERY-07, DISCOVERY-08, DISCOVERY-09, DISCOVERY-10]

must_haves:
  truths:
    - "parent_node_id is set in _save_node and _respawn_nodes (evidence: frontier.py line numbers)"
    - "Node hierarchy can be reconstructed from parent_node_id links"
    - "Pagination behavior corrected: either true depth exploration or documented fallback semantics"
    - "academic_only filtering is active OR dead code removed with rationale"
    - "exhausted_modes persisted in checkpoint and restored on restart"
    - "enqueue_job implements backpressure (queue depth check, circuit breaker, or throttling)"
  artifacts:
    - path: ".planning/gauntlet_phases/phase06_discovery/GAPCLOSURE-06-02-SUMMARY.md"
      provides: "parent_node_id fix applied, schema migration if needed, test evidence"
    - path: ".planning/gauntlet_phases/phase06_discovery/GAPCLOSURE-06-03-SUMMARY.md"
      provides: "deep mining behavior corrected or documented, test results showing page 2+ reach"
    - path: ".planning/gauntlet_phases/phase06_discovery/GAPCLOSURE-06-04-SUMMARY.md"
      provides: "academic_only enforcement wired or code cleaned up"
    - path: ".planning/gauntlet_phases/phase06_discovery/GAPCLOSURE-06-05-SUMMARY.md"
      provides: "exhausted_modes checkpoint/restore working"
    - path: ".planning/gauntlet_phases/phase06_discovery/GAPCLOSURE-06-06-SUMMARY.md"
      provides: "backpressure mechanism in place, queue depth bounded"
  key_links:
    - from: "GAPCLOSURE-06-02-SUMMARY.md"
      to: "TAXONOMY_GENERATION_AUDIT.md"
      via: "closes parent_node_id gap"
    - from: "GAPCLOSURE-06-03-SUMMARY.md"
      to: "SEARCH_BEHAVIOR_REPORT.md"
      via: "fixes break-on-first-success inversion"
    - from: "GAPCLOSURE-06-04-SUMMARY.md"
      to: "URL_SELECTION_HEURISTICS.md"
      via: "academic_only enforcement or cleanup"
    - from: "GAPCLOSURE-06-05-SUMMARY.md"
      to: "DISCOVERY_AUDIT.md §Area 4"
      via: "persistent exhausted_modes"
    - from: "GAPCLOSURE-06-06-SUMMARY.md"
      to: "DISCOVERY_AUDIT.md §Area 6"
      via: "bounded queue growth"

objective: |
  Close the 5 discovery audit gaps identified in Phase 06-01 by making targeted code changes to enforce behavior that previously existed only as structure or claim.

  This is a gap-closure phase. Each subplan (06-02 through 06-06) addresses one specific finding from the audit.

  DO NOT expand scope. DO NOT redesign unrelated components. Make minimal surgical changes to align implementation with claims.

tasks:

- task type: auto
  name: "06-02: Set parent_node_id on node creation"
  read_first:
    - /home/bamn/Sheppard/src/research/acquisition/frontier.py (lines 157-171, 329-352)
    - /home/bamn/Sheppard/src/research/domain_schema.py (line 107)
  action: |
    Modify `_save_node` (frontier.py lines 157-171) to accept and set `parent_node_id` on the MissionNode constructor. Also modify `_respawn_nodes` (lines 329-352) to pass the parent's node_id when creating child nodes.

    Steps:
    1. In `_save_node`, add parameter `parent_node_id: Optional[str] = None`
    2. Construct MissionNode with `parent_node_id=parent_node_id`
    3. In `_respawn_nodes`, call `_save_node(..., parent_node_id=parent_node.node_id)`
    4. Verify MissionNode already has the field (domain_schema.py line 107) — no schema change needed
    5. Write a quick test: create parent node, spawn children, verify parent_node_id linkage in DB

    Commit with message: `fix(06-discovery): set parent_node_id in _save_node and _respawn_nodes`
  verify:
    automated:
      - grep -n "def _save_node" /home/bamn/Sheppard/src/research/acquisition/frontier.py | grep "parent_node_id"
      - grep -n "_save_node.*parent_node_id=" /home/bamn/Sheppard/src/research/acquisition/frontier.py
      - grep "parent_node_id" /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/GAPCLOSURE-06-02-SUMMARY.md

- task type: auto
  name: "06-03: Fix deep mining to actually explore pages 2–5"
  read_first:
    - /home/bamn/Sheppard/src/research/acquisition/crawler.py (lines 294-330)
  action: |
    The current logic breaks on first page with any new URLs. Choose ONE approach:

    Option A (Depth Exploration): Remove the break condition entirely. Iterate all 5 pages and collect URLs from all pages. If the goal is breadth-first across pages, this is the correct fix.

    Option B (Documented Fallback): Keep the break but document it as intentional dedup fallback, and adjust claims to match. Since the audit classified this as PARTIAL/MISCHARACTERIZED, you should likely fix the behavior to match the "deep mines up to page 5" claim.

    Recommended: Implement Option A. Replace:
    ```python
    if page_new_count > 0:
        break
    ```
    with logic that continues through all pages but still skips already-visited URLs. Keep the inner early-exit on empty result (line 300) — that's fine.

    Ensure tests pass: create scenario where page 1 has all known URLs, verify pages 2–5 still fetched.

    Commit: `fix(06-discovery): deep mining iterates all pages without early break`
  verify:
    automated:
      - grep -A 2 "for page in range(1, 6)" /home/bamn/Sheppard/src/research/acquisition/crawler.py | grep -v "break" || echo "break still present"
      - grep "page_new_count > 0" /home/bamn/Sheppard/src/research/acquisition/crawler.py && echo "break condition still exists" || echo "break removed"
      - test -f /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/GAPCLOSURE-06-03-SUMMARY.md

- task type: auto
  name: "06-04: Activate academic_only filtering or remove dead code"
  read_first:
    - /home/bamn/Sheppard/src/research/acquisition/crawler.py (lines 71, 185, 294-330)
    - /home/bamn/Sheppard/src/core/system.py (lines 125-128)
  action: |
    Two valid paths:

    Path A (Enforcement): Set `academic_only=True` when constructing `FirecrawlLocalClient` in `system.py` (lines 125-128). Additionally, add a pre-enqueue check in `discover_and_enqueue` that calls `_is_academic(url)` and skips non-academic URLs when `self.academic_only` is True.

    Path B (Cleanup): If academic filtering is not desired, remove the `academic_only` flag and `_is_academic` function to avoid dead code. Update documentation to remove claims about academic filtering.

    Given the original claims included academic whitelist filtering, **Path A is recommended**.

    Implementation:
    1. In `system.py`, change construction to: `FirecrawlLocalClient(..., academic_only=True)`
    2. In `crawler.py`, inside `discover_and_enqueue` before `await self.enqueue_job(url, ...)`, add:
       ```python
       if self.academic_only and not self._is_academic(url):
           continue
       ```
    3. Verify the flag is properly passed through initializers.

    Commit: `fix(06-discovery): enforce academic_only filtering at enqueue`
  verify:
    automated:
      - grep "academic_only=True" /home/bamn/Sheppard/src/core/system.py
      - grep -n "if self.academic_only" /home/bamn/Sheppard/src/research/acquisition/crawler.py
      - test -f /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/GAPCLOSURE-06-04-SUMMARY.md

- task type: auto
  name: "06-05: Persist exhausted_modes across restarts"
  read_first:
    - /home/bamn/Sheppard/src/research/acquisition/frontier.py (lines 143-148, 286-310)
  action: |
    Currently `_load_checkpoint` resets `exhausted_modes=set()`. Need to:
    1. Modify checkpoint save to include `exhausted_modes` (dictionary mapping node_id → list of exhausted modes)
    2. Modify `_load_checkpoint` to restore that state

    Implementation:
    - In `_save_checkpoint()`, add `'exhausted_modes': {nid: list(modes) for nid, modes in self.exhausted_modes.items()}`
    - In `_load_checkpoint()`, after loading `data`, set `self.exhausted_modes = {k: set(v) for k, v in data.get('exhausted_modes', {})}`

    Note: `exhausted_modes` may be per-node. Ensure the data structure correctly restores per-node sets.

    Also verify that the frontier still functions if checkpoint has no `exhausted_modes` (first run).

    Commit: `fix(06-discovery): checkpoint exhausted_modes to persist across restarts`
  verify:
    automated:
      - grep -n "exhausted_modes" /home/bamn/Sheppard/src/research/acquisition/frontier.py | grep "save_checkpoint\|_load_checkpoint"
      - grep "'exhausted_modes'" /home/bamn/Sheppard/src/research/acquisition/frontier.py
      - test -f /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/GAPCLOSURE-06-05-SUMMARY.md

- task type: auto
  name: "06-06: Add queue backpressure mechanism"
  read_first:
    - /home/bamn/Sheppard/src/memory/adapters/redis.py (lines 83-84)
    - /home/bamn/Sheppard/src/research/acquisition/frontier.py (enqueue calls)
  action: |
    Implement a simple circuit breaker: before `rpush`, check queue depth with `llen`. If depth exceeds threshold (configurable, e.g., 10,000), pause frontier or reject new URLs with a log warning.

    Minimal implementation:
    1. Add `MAX_QUEUE_DEPTH = 10000` constant (or read from config)
    2. Modify `enqueue_job`:
       ```python
       depth = await self.redis.llen(self.queue_key)
       if depth >= MAX_QUEUE_DEPTH:
           logger.warning(f"Queue depth {depth} exceeds limit — rejecting job")
           return False  # or raise BackpressureError
       await self.redis.rpush(self.queue_key, serialize(job))
       return True
       ```
    3. Frontier should handle rejected jobs (drop or backoff retry)

    This is the minimal viable backpressure. Better solutions (pause/resume signals) can be Phase 07.

    Commit: `fix(06-discovery): add queue depth check to enqueue_job as circuit breaker`
  verify:
    automated:
      - grep -n "llen" /home/bamn/Sheppard/src/memory/adapters/redis.py
      - grep "MAX_QUEUE_DEPTH\|queue_depth" /home/bamn/Sheppard/src/memory/adapters/redis.py
      - test -f /home/bamn/Sheppard/.planning/gauntlet_phases/phase06_discovery/GAPCLOSURE-06-06-SUMMARY.md

done: |
  All 5 gap-closure tasks completed. Each audit finding addressed with minimal code changes. Verification shows:
  - parent_node_id set on node creation
  - deep mining iterates all pages (or behavioral change documented)
  - academic_only filtering active
  - exhausted_modes persisted in checkpoint
  - queue depth check prevents unbounded growth

  Phase 06 now achieves FULL PASS on discovery layer claims, or at worst MINOR PARTIAL if any behavioral adjustments are deferred by design.

---
stage: draft
estimate_days: 3-5
validate: true
wave_structure:
  wave1: ["06-01"] (audit — already complete)
  wave2: ["06-02", "06-03", "06-04", "06-05", "06-06"] (gap closures — can run in parallel if independent)