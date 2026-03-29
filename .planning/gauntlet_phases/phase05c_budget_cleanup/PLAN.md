---
phase: 05c-budget-cleanup
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/research/acquisition/budget.py
  - src/research/condensation/pipeline.py
  - src/core/system.py
autonomous: true
gap_closure: true
requirements:
  - A5
  - A6

must_haves:
  truths:
    - "No file in the V3 control path uses topic_id as a BudgetMonitor parameter name"
    - "budget.py contains zero instances of the string topic_id"
    - "pipeline.py bridge shim (topic_id = mission_id) is gone"
    - "Budget threshold callbacks fire with mission_id as the first argument"
    - "record_condensation_result is called with mission_id= keyword, not topic_id="
    - "system.py contains no topic_id= keyword arguments in BudgetMonitor method calls"
  artifacts:
    - path: "src/research/acquisition/budget.py"
      provides: "BudgetMonitor and TopicBudget with mission_id throughout"
      excludes: "topic_id"
    - path: "src/research/condensation/pipeline.py"
      provides: "DistillationPipeline with bridge shim removed"
      excludes: "topic_id = mission_id  # Bridge for budget hooks"
    - path: "src/core/system.py"
      provides: "register_topic call using mission_id= keyword"
      excludes: "topic_id=mission_id"
  key_links:
    - from: "src/research/condensation/pipeline.py:138"
      to: "src/research/acquisition/budget.py:record_condensation_result"
      via: "keyword arg mission_id="
      pattern: "record_condensation_result\\(\\s*mission_id="
    - from: "src/research/acquisition/budget.py:_check_thresholds"
      to: "condensation_callback"
      via: "first positional arg carrying mission_id value"
      pattern: "condensation_callback\\(mission_id"
    - from: "src/core/system.py:201"
      to: "src/research/acquisition/budget.py:register_topic"
      via: "keyword arg mission_id="
      pattern: "register_topic\\(\\s*mission_id="
---

<objective>
Rename all `topic_id` parameter names within the BudgetMonitor control path to `mission_id`,
remove the one-line bridge shim in pipeline.py, update ExtractionCluster to carry `mission_id`,
and fix the call site in system.py that still passes `topic_id=` as a keyword argument.

Purpose: Phase 05C gap closure — eliminates A5 and A6 findings from PHASE-05-VERIFICATION.md.
V2 bridge terminology is gone; mission_id is the sole runtime identifier in the V3 control path.

Output:
- src/research/acquisition/budget.py — zero occurrences of `topic_id`
- src/research/condensation/pipeline.py — bridge shim removed, callers updated
- src/core/system.py — register_topic call uses mission_id= keyword, bridge comment removed
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/gauntlet_phases/phase05c_budget_cleanup/PHASE-05C-PLAN.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rename topic_id to mission_id throughout budget.py</name>

  <read_first>
    src/research/acquisition/budget.py  (full file — all occurrences confirmed before edit)
  </read_first>

  <files>src/research/acquisition/budget.py</files>

  <action>
Perform the following renames inside src/research/acquisition/budget.py.
Make every change listed; do not change anything else.

1. TopicBudget dataclass (line 34):
   BEFORE: `    topic_id: str`
   AFTER:  `    mission_id: str`

2. BudgetMonitor docstring (line 76):
   BEFORE: `    The condensation_callback is called with (topic_id, priority) when a`
   AFTER:  `    The condensation_callback is called with (mission_id, priority) when a`

3. register_topic method — parameter and body (lines 94-111):
   - Rename parameter `topic_id: str` → `mission_id: str`
   - Line 100: `"""Register a topic for budget tracking."""` — leave unchanged
   - Line 102-106: `TopicBudget(topic_id=topic_id, ...)` → `TopicBudget(mission_id=mission_id, ...)`
   - Line 107: `self._budgets[topic_id] = budget` → `self._budgets[mission_id] = budget`
   (The log line on 108-110 does not reference topic_id, leave it unchanged.)

4. record_bytes method (lines 113-125):
   - Rename parameter `topic_id: str` → `mission_id: str`
   - Line 119: `if topic_id not in self._budgets:` → `if mission_id not in self._budgets:`
   - Line 120: `logger.warning(f"[Budget] Unknown topic_id: {topic_id}")` →
               `logger.warning(f"[Budget] Unknown mission_id: {mission_id}")`
   - Line 122: `budget = self._budgets[topic_id]` → `budget = self._budgets[mission_id]`
   - Line 125: `await self._check_thresholds(topic_id)` → `await self._check_thresholds(mission_id)`

5. record_condensation_result method (lines 127-150):
   - Rename parameter `topic_id: str` → `mission_id: str`
   - Line 138: `if topic_id not in self._budgets:` → `if mission_id not in self._budgets:`
   - Line 140: `budget = self._budgets[topic_id]` → `budget = self._budgets[mission_id]`
   (Lines 141-150 reference only `budget.*`, no topic_id — leave unchanged.)

6. get_status method (line 152-153):
   - Rename parameter `topic_id: str` → `mission_id: str`
   - Line 153: `return self._budgets.get(topic_id)` → `return self._budgets.get(mission_id)`

7. can_crawl method (lines 158-168):
   - Rename parameter `topic_id: str` → `mission_id: str`
   - Line 163: `budget = self._budgets.get(topic_id)` → `budget = self._budgets.get(mission_id)`

8. _check_thresholds method (lines 170-208):
   - Rename parameter `topic_id: str` → `mission_id: str`
   - Line 176: `budget = self._budgets[topic_id]` → `budget = self._budgets[mission_id]`
   - Line 207: `self.condensation_callback(topic_id, priority)` →
               `self.condensation_callback(mission_id, priority)`

9. run_monitor_loop (lines 219-220):
   - Line 219: `for topic_id in list(self._budgets.keys()):` →
               `for mission_id in list(self._budgets.keys()):`
   - Line 220: `await self._check_thresholds(topic_id)` →
               `await self._check_thresholds(mission_id)`

After all edits the file must contain ZERO occurrences of the string `topic_id`.
  </action>

  <verify>
    <automated>grep -n "topic_id" /home/bamn/Sheppard/src/research/acquisition/budget.py; echo "exit:$?"</automated>
  </verify>

  <acceptance_criteria>
    - `grep topic_id src/research/acquisition/budget.py` returns no output (exit 1 = no match).
    - `grep -n "mission_id" src/research/acquisition/budget.py` returns at minimum lines covering:
      TopicBudget.mission_id field, register_topic(mission_id), record_bytes(mission_id),
      record_condensation_result(mission_id), get_status(mission_id), can_crawl(mission_id),
      _check_thresholds(mission_id), condensation_callback(mission_id, priority),
      run_monitor_loop loop variable mission_id.
    - Python can import the module without error:
      `python -c "from src.research.acquisition.budget import BudgetMonitor, TopicBudget"` exits 0.
  </acceptance_criteria>

  <done>
    budget.py has zero occurrences of topic_id. All method signatures and internal
    variable names use mission_id. TopicBudget.mission_id is the dataclass field name.
    Module imports cleanly.
  </done>
</task>

<task type="auto">
  <name>Task 2: Remove bridge shim from pipeline.py and fix all budget call sites</name>

  <read_first>
    src/research/condensation/pipeline.py  (full file — confirm line numbers before edit)
  </read_first>

  <files>src/research/condensation/pipeline.py</files>

  <action>
Make the following targeted edits inside src/research/condensation/pipeline.py.

1. Remove bridge shim (line 45):
   DELETE this line entirely:
     `        topic_id = mission_id # Bridge for budget hooks`
   The method body of `run()` already uses `mission_id` everywhere after line 45;
   the only downstream reference to `topic_id` after this shim is in line 139
   (handled below). After deletion, line 45 becomes line 46 etc — renumber mentally.

2. Fix budget.record_condensation_result call (was line 139, now one line earlier):
   BEFORE: `                topic_id=topic_id,`
   AFTER:  `                mission_id=mission_id,`
   This is inside the `# 7. Budget Feedback` block; the full call becomes:
   ```python
   await self.budget.record_condensation_result(
       mission_id=mission_id,
       raw_bytes_freed=sum(len(str(s).encode()) for s in sources),
       condensed_bytes_added=total_atoms * 500
   )
   ```

3. Rename ExtractionCluster.topic_id field (line 30):
   BEFORE: `    topic_id: str`
   AFTER:  `    mission_id: str`

4. Fix ExtractionCluster instantiation in _cluster_sources (was line 147):
   BEFORE: `clusters = [ExtractionCluster(topic_id=sources[0]['topic_id'], concept="batch_general", sources=sources)]`
   AFTER:  `clusters = [ExtractionCluster(mission_id=sources[0].get('mission_id', sources[0].get('topic_id', '')), concept="batch_general", sources=sources)]`
   Rationale: the DB row may still carry `topic_id` as a column name (DB schema not in scope),
   so use .get() with fallback to avoid a KeyError. The ExtractionCluster field is now mission_id.

5. Rename stub method parameters (lines 150, 155):
   `async def resolve_contradictions(self, topic_id: str):` → `async def resolve_contradictions(self, mission_id: str):`
   `async def consolidate_atoms(self, topic_id: str):` → `async def consolidate_atoms(self, mission_id: str):`
   Bodies are `pass` — no further changes needed.

After all edits, the only remaining `topic_id` occurrences in pipeline.py should be:
  - String literals inside DB row reads (e.g. `mission_row.get("topic_id")` at ~line 94) — these
    reference the actual database column name and are NOT renamed (DB schema out of scope).
  - The `.get('topic_id', '')` fallback added in step 4 above.
  All live parameter names and variable names must use mission_id.
  </action>

  <verify>
    <automated>
      grep -n "topic_id = mission_id" /home/bamn/Sheppard/src/research/condensation/pipeline.py; echo "bridge_exit:$?"
      grep -n "topic_id=topic_id" /home/bamn/Sheppard/src/research/condensation/pipeline.py; echo "kwarg_exit:$?"
      grep -n "def resolve_contradictions\|def consolidate_atoms" /home/bamn/Sheppard/src/research/condensation/pipeline.py
      grep -n "mission_id: str" /home/bamn/Sheppard/src/research/condensation/pipeline.py
      python -c "from src.research.condensation.pipeline import DistillationPipeline, ExtractionCluster; print('OK')" 2>&1
    </automated>
  </verify>

  <acceptance_criteria>
    - `grep "topic_id = mission_id" src/research/condensation/pipeline.py` returns no output (bridge gone).
    - `grep "topic_id=topic_id" src/research/condensation/pipeline.py` returns no output (old kwarg gone).
    - `grep "mission_id=mission_id" src/research/condensation/pipeline.py` returns the budget callback line.
    - ExtractionCluster dataclass field is `mission_id: str` (grep confirms).
    - Both `resolve_contradictions` and `consolidate_atoms` stub signatures show `mission_id: str`, not `topic_id: str`.
    - `python -c "from src.research.condensation.pipeline import DistillationPipeline, ExtractionCluster"` exits 0.
    - `grep -n "topic_id" src/research/condensation/pipeline.py` shows ONLY DB column string literals
      (`.get("topic_id"`) — no live variable names or parameter names remain.
  </acceptance_criteria>

  <done>
    Bridge shim removed. budget.record_condensation_result called with mission_id= keyword.
    ExtractionCluster carries mission_id field. Stub method params renamed.
    Only DB-column string literals containing "topic_id" remain in the file.
    Module imports cleanly.
  </done>
</task>

<task type="auto">
  <name>Task 3: Fix register_topic call site in system.py</name>

  <read_first>
    src/core/system.py lines 195-210 (confirm the call site before editing)
  </read_first>

  <files>src/core/system.py</files>

  <action>
Task 1 renames `register_topic`'s parameter from `topic_id` to `mission_id`. The call site
in system.py still passes `topic_id=mission_id` as an explicit keyword argument, which will
raise `TypeError: register_topic() got an unexpected keyword argument 'topic_id'` at runtime.

Make the following targeted edit at line 201 (inside the `# 3. Register with Budget Monitor` block):

BEFORE (lines 200-205):
```python
        # 3. Register with Budget Monitor (will be migrated to mission_id in Phase 03)
        self.budget.register_topic(
            topic_id=mission_id,  # Bridge: use mission_id as topic_id until BudgetMonitor migrates
            topic_name=topic_name,
            ceiling_gb=ceiling_gb,
        )
```

AFTER:
```python
        # 3. Register with Budget Monitor
        self.budget.register_topic(
            mission_id=mission_id,
            topic_name=topic_name,
            ceiling_gb=ceiling_gb,
        )
```

Changes made:
- `topic_id=mission_id,` → `mission_id=mission_id,`
- Remove the inline bridge comment (`# Bridge: use mission_id as topic_id until BudgetMonitor migrates`)
- Update the block comment to remove the stale Phase 03 migration note

Do not touch any other lines in system.py.
  </action>

  <verify>
    <automated>grep -n "topic_id=" /home/bamn/Sheppard/src/core/system.py | grep -E "register_topic|budget\."; echo "exit:$?"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -n "topic_id=" src/core/system.py | grep -E "register_topic|budget\."` returns no output.
      Note: `ResearchMission(topic_id=mission_id, ...)` at line 192 is intentionally preserved —
      it is a DB model constructor argument matching the database schema column name, not a
      BudgetMonitor call. This line is out of scope and must not be changed.
    - `grep -n "mission_id=mission_id" src/core/system.py` returns the register_topic call line.
    - `python -c "import src.core.system"` exits 0 (import smoke test, environment permitting).
  </acceptance_criteria>

  <done>
    system.py line 201 uses `mission_id=mission_id,` as the keyword argument.
    The bridge comment is removed. No remaining `topic_id=` keyword arguments exist
    in BudgetMonitor method calls anywhere in system.py.
    Note: `ResearchMission(topic_id=mission_id)` at line 192 is intentionally preserved for
    DB schema compatibility — it maps the runtime mission_id value into the database column
    named topic_id and is not a BudgetMonitor call.
  </done>
</task>

</tasks>

<verification>
Run all checks after all three tasks complete:

```bash
# 1. budget.py: zero topic_id
grep -c "topic_id" src/research/acquisition/budget.py

# 2. pipeline.py: no bridge shim, no live topic_id params
grep -n "topic_id = mission_id" src/research/condensation/pipeline.py
grep -n "topic_id=topic_id" src/research/condensation/pipeline.py

# 3. system.py: no topic_id= keyword args in BudgetMonitor calls
grep -n "topic_id=" src/core/system.py | grep -E "register_topic|budget\."

# 4. Import smoke test
python -c "
from src.research.acquisition.budget import BudgetMonitor, TopicBudget, BudgetConfig
from src.research.condensation.pipeline import DistillationPipeline, ExtractionCluster
b = TopicBudget(mission_id='test-id', topic_name='test', ceiling_bytes=1000)
print('TopicBudget.mission_id =', b.mission_id)
e = ExtractionCluster(mission_id='test-id', concept='test')
print('ExtractionCluster.mission_id =', e.mission_id)
print('ALL PASS')
"
```

Expected: grep count = 0 for budget.py, no output for bridge/kwarg greps,
no output for topic_id= BudgetMonitor calls in system.py, ALL PASS printed.
</verification>

<success_criteria>
- grep finds zero occurrences of `topic_id` as a variable/parameter name in budget.py
- Bridge shim line removed from pipeline.py
- budget.record_condensation_result called with mission_id= keyword argument
- ExtractionCluster.mission_id field confirmed by import smoke test
- No import errors from either module
- `grep -n "topic_id=" src/core/system.py | grep -E "register_topic|budget\."` returns no output
- system.py register_topic call uses `mission_id=mission_id,` keyword argument
</success_criteria>

<output>
After completion, create `.planning/gauntlet_phases/phase05c_budget_cleanup/SUMMARY.md`
covering: what was renamed, what was removed, what DB column string literals were intentionally
left unchanged, the system.py call site fix, and the import smoke test output confirming success.
</output>
