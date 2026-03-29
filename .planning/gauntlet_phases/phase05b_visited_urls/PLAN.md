---
phase: 05b-visited-urls
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/memory/storage_adapter.py
  - src/research/acquisition/frontier.py
autonomous: true
requirements:
  - A10
must_haves:
  truths:
    - "Restarting AdaptiveFrontier for an existing mission populates self.visited_urls from corpus.sources, not from an empty set"
    - "URLs already stored in corpus.sources for a mission are excluded from re-enqueue on restart"
    - "get_visited_urls returns a Set[str] of normalized_url values for a given mission_id"
  artifacts:
    - path: "src/memory/storage_adapter.py"
      provides: "get_visited_urls method on CorpusStore protocol and SheppardStorageAdapter"
      contains: "get_visited_urls"
    - path: "src/research/acquisition/frontier.py"
      provides: "_load_checkpoint calls get_visited_urls to rebuild visited set"
      contains: "get_visited_urls"
  key_links:
    - from: "src/research/acquisition/frontier.py:_load_checkpoint"
      to: "src/memory/storage_adapter.py:get_visited_urls"
      via: "await self.sm.adapter.get_visited_urls(self.mission_id)"
      pattern: "get_visited_urls\\(self\\.mission_id\\)"
    - from: "src/memory/storage_adapter.py:get_visited_urls"
      to: "corpus.sources"
      via: "self.list_sources(mission_id) plucking normalized_url"
      pattern: "list_sources.*mission_id"
---

<objective>
Close gap A10: persist visited_urls across AdaptiveFrontier restarts by wiring the existing
corpus.sources table as the source of truth for the visited URL set.

Purpose: Every URL ingested is already recorded in corpus.sources.normalized_url. The frontier
just needs to query that column on startup to rebuild the in-memory dedup set rather than
starting empty every run.

Output:
- get_visited_urls(mission_id) method added to CorpusStore protocol + SheppardStorageAdapter
- _load_checkpoint updated to call that method and assign the result to self.visited_urls
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/gauntlet_phases/phase05b_visited_urls/PHASE-05B-PLAN.md

<interfaces>
<!-- Key contracts executor needs. Extracted from codebase. -->

From src/memory/storage_adapter.py (CorpusStore protocol, lines 87-106):
```python
class CorpusStore(Protocol):
    async def register_source(self, source: JsonDict) -> None: ...
    async def get_source(self, source_id: str) -> JsonDict | None: ...
    async def get_source_by_url_hash(self, normalized_url_hash: str) -> JsonDict | None: ...
    async def list_sources(self, mission_id: str, topic_id: str | None = None) -> list[JsonDict]: ...
    # ... (add get_visited_urls here)
```

From src/memory/storage_adapter.py (SheppardStorageAdapter.list_sources, lines 526-529):
```python
async def list_sources(self, mission_id: str, topic_id: str | None = None) -> list[JsonDict]:
    where: JsonDict = {"mission_id": mission_id}
    if topic_id is not None: where["topic_id"] = topic_id
    return await self.pg.fetch_many("corpus.sources", where=where, order_by="created_at DESC")
```
Each row in corpus.sources contains a "normalized_url" key (str or None).

From src/research/acquisition/frontier.py (_load_checkpoint, lines 136-154):
```python
async def _load_checkpoint(self):
    """Restore previous state from DB."""
    console.print(...)
    db_nodes = await self.sm.adapter.list_mission_nodes(self.mission_id)
    for n in db_nodes:
        self.nodes[n['label']] = FrontierNode(...)

    # FIXME: V3 visited_urls persistence not implemented; will lose dedup state across restarts
    # self.visited_urls = await self.sm.adapter.get_visited_urls(self.mission_id)  # Not yet available

    if self.nodes:
        console.print(...)
```
self.visited_urls is typed as Set[str] (initialized in __init__ as set()).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add get_visited_urls to CorpusStore protocol and SheppardStorageAdapter</name>
  <files>src/memory/storage_adapter.py</files>
  <read_first>
    - src/memory/storage_adapter.py lines 87-106 (CorpusStore protocol — insert declaration after list_sources)
    - src/memory/storage_adapter.py lines 526-529 (list_sources implementation — new method goes right after)
  </read_first>
  <action>
**Step 1 — Add protocol stub to CorpusStore (after the list_sources stub, line ~91):**

```python
    async def get_visited_urls(self, mission_id: str) -> set[str]: ...
```

Place it immediately after:
    async def list_sources(self, mission_id: str, topic_id: str | None = None) -> list[JsonDict]: ...

**Step 2 — Add concrete implementation to SheppardStorageAdapter (after list_sources, line ~529):**

```python
    async def get_visited_urls(self, mission_id: str) -> set[str]:
        rows = await self.list_sources(mission_id)
        return {r["normalized_url"] for r in rows if r.get("normalized_url")}
```

Place it immediately after the closing line of list_sources:
    return await self.pg.fetch_many("corpus.sources", where=where, order_by="created_at DESC")

No new imports needed. `set` is a builtin; `list_sources` already exists on `self`.
  </action>
  <verify>
    <automated>cd /home/bamn/Sheppard && python -c "
import ast, sys
src = open('src/memory/storage_adapter.py').read()
tree = ast.parse(src)
methods = [n.name for c in ast.walk(tree) if isinstance(c, ast.ClassDef) for n in ast.walk(c) if isinstance(n, ast.AsyncFunctionDef)]
assert 'get_visited_urls' in methods, 'get_visited_urls not found'
# Verify it appears twice (protocol stub + concrete impl)
assert src.count('get_visited_urls') >= 2, f'Expected >=2 occurrences, got {src.count(\"get_visited_urls\")}'
print('PASS: get_visited_urls present in both CorpusStore and SheppardStorageAdapter')
"
    </automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "get_visited_urls" src/memory/storage_adapter.py` returns at least 2 lines (one in CorpusStore, one in SheppardStorageAdapter)
    - The SheppardStorageAdapter implementation body contains `list_sources` and `normalized_url`
    - `python -c "from src.memory.storage_adapter import SheppardStorageAdapter"` exits 0 (no syntax errors)
  </acceptance_criteria>
  <done>get_visited_urls declared in CorpusStore protocol and implemented in SheppardStorageAdapter; method queries corpus.sources via list_sources and returns a set[str] of normalized_url values.</done>
</task>

<task type="auto">
  <name>Task 2: Wire _load_checkpoint in AdaptiveFrontier to populate self.visited_urls</name>
  <files>src/research/acquisition/frontier.py</files>
  <read_first>
    - src/research/acquisition/frontier.py lines 136-160 (_load_checkpoint — replace the FIXME block)
  </read_first>
  <action>
In `_load_checkpoint`, replace the two FIXME comment lines (lines 150-151):

**Remove:**
```python
        # FIXME: V3 visited_urls persistence not implemented; will lose dedup state across restarts
        # self.visited_urls = await self.sm.adapter.get_visited_urls(self.mission_id)  # Not yet available
```

**Replace with:**
```python
        self.visited_urls = await self.sm.adapter.get_visited_urls(self.mission_id)
```

Then, immediately after the existing `if self.nodes:` logging block (which prints the node count),
add a parallel log line for visited URLs:

```python
        if self.visited_urls:
            console.print(f"[dim]  - Pre-loaded {len(self.visited_urls)} visited URLs from DB.[/dim]")
```

The full updated block should read:

```python
        self.visited_urls = await self.sm.adapter.get_visited_urls(self.mission_id)

        if self.nodes:
            console.print(f"[dim]  - Pre-loaded {len(self.nodes)} research nodes from DB.[/dim]")
        if self.visited_urls:
            console.print(f"[dim]  - Pre-loaded {len(self.visited_urls)} visited URLs from DB.[/dim]")
```

No imports needed. `self.sm.adapter` is already used on the line above for `list_mission_nodes`.
  </action>
  <verify>
    <automated>cd /home/bamn/Sheppard && python -c "
import ast
src = open('src/research/acquisition/frontier.py').read()
assert 'FIXME' not in src, 'FIXME comment still present — not removed'
assert 'get_visited_urls' in src, 'get_visited_urls call not found in frontier.py'
assert 'Not yet available' not in src, 'Old commented-out line still present'
tree = ast.parse(src)
print('PASS: frontier.py parses cleanly and FIXME block is replaced')
"
    </automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "FIXME" src/research/acquisition/frontier.py` returns no output
    - `grep -n "get_visited_urls" src/research/acquisition/frontier.py` returns exactly 1 line inside `_load_checkpoint`
    - `grep -n "Pre-loaded.*visited URLs" src/research/acquisition/frontier.py` returns 1 line
    - `python -c "from src.research.acquisition.frontier import AdaptiveFrontier"` exits 0
  </acceptance_criteria>
  <done>_load_checkpoint calls self.sm.adapter.get_visited_urls(self.mission_id) and assigns the result to self.visited_urls; the FIXME comment block is fully removed; a console log confirms how many URLs were restored.</done>
</task>

</tasks>

<verification>
After both tasks complete, run:

```bash
cd /home/bamn/Sheppard

# 1. Syntax / import checks
python -c "from src.memory.storage_adapter import SheppardStorageAdapter; print('adapter OK')"
python -c "from src.research.acquisition.frontier import AdaptiveFrontier; print('frontier OK')"

# 2. Structural checks
grep -n "get_visited_urls" src/memory/storage_adapter.py
grep -n "get_visited_urls" src/research/acquisition/frontier.py
grep -c "FIXME" src/research/acquisition/frontier.py   # must be 0

# 3. Confirm the implementation body is correct
grep -A3 "async def get_visited_urls" src/memory/storage_adapter.py
```

Expected output:
- `adapter OK`, `frontier OK`
- Two lines in storage_adapter.py (protocol + impl)
- One line in frontier.py (inside _load_checkpoint)
- FIXME count = 0
- Implementation body contains `list_sources` and `normalized_url`
</verification>

<success_criteria>
- get_visited_urls(mission_id) exists in CorpusStore protocol (stub) and SheppardStorageAdapter (implementation using list_sources + normalized_url pluck)
- _load_checkpoint in AdaptiveFrontier assigns self.visited_urls from get_visited_urls on every startup
- No FIXME comment remains in frontier.py
- Both files parse without errors (ast.parse passes)
- On restart, a mission with N previously ingested URLs will have self.visited_urls pre-populated with N entries, preventing re-enqueue
</success_criteria>

<output>
After completion, create `.planning/gauntlet_phases/phase05b_visited_urls/SUMMARY.md` describing:
- What changed (method added, FIXME removed)
- Why (gap A10: visited_urls lost on restart)
- Verification evidence (grep output confirming presence)
- Status: PASS or FAIL
</output>
