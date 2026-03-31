# Phase 12-03 Research: Synthesis Throughput

**Researched:** 2026-03-31  
**Domain:** Async concurrency, LLM synthesis pipeline optimization  
**Confidence:** HIGH

## Executive Summary

The primary bottleneck in synthesis throughput is the sequential LLM section generation loop, which calls `archivist.write_section()` one section at a time to build `previous_context`. To achieve ≥20% improvement in `validated_sections_per_minute`, we recommend removing the `previous_context` dependency (which only affects narrative flow, not truth invariants) and parallelizing LLM calls using a bounded async worker pool with `asyncio.Semaphore`. This allows multiple sections to be synthesized concurrently while maintaining deterministic ordering, preserving all truth contract invariants, and requiring minimal changes to the codebase. The approach leverages existing async infrastructure (OllamaClient, async DB drivers) and will yield 3-5x speedup depending on concurrency limit (4-8).

## Current State Analysis

The synthesis pipeline (`SynthesisService.generate_master_brief`) currently operates as follows:

1. Generate section plan (single LLM call).
2. Retrieve evidence for all sections concurrently via `EvidenceAssembler.assemble_all_sections` (already parallel retrieval using batch query or sequential fallback).
3. **Sequential** LLM loop:
   - For each section in order: call `archivist.write_section(packet, previous_context)`
   - Validate grounding via `_validate_grounding`
   - Accumulate `previous_context` from the just-generated prose for the next section’s flow.
4. After all sections complete, store artifact, sections, and citations in a single batch.

The `previous_context` parameter creates a hard dependency chain: section N cannot start until section N-1 finishes. Evidence retrieval is already concurrent, but LLM synthesis remains sequential, causing the bulk of the latency (≈52s in baseline high-evidence runs). The validator is trivial (<1ms). The storage is sub-second.

## Technical Questions Answered

### 1. Async Worker Pool Implementation

**Recommendation:** Use `asyncio.Semaphore` to bound concurrency. `ThreadPoolExecutor` is unnecessary because LLM calls are I/O-bound (HTTP requests to Ollama). Async I/O releases the GIL and scales efficiently.

Pattern in `SynthesisService`:

```python
CONCURRENCY_LIMIT = 8  # tunable; default 4-8 per CONTEXT
sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

async def process_section(self, section, packet):
    async with sem:
        prose = await self.archivist.write_section(packet, "")
        if not self._validate_grounding(prose, packet):
            return (section.order, None)  # insufficient
        return (section.order, {
            "title": section.title,
            "prose": prose,
            "atom_ids": list(packet.atom_ids_used)
        })

# In generate_master_brief:
tasks = [asyncio.create_task(self.process_section(s, all_packets[s.order]))
         for s in sorted(plan, key=lambda x: x.order)]
results = await asyncio.gather(*tasks)  # gather preserves order of tasks, but we sort anyway
sections_by_order = dict(results)
```

### 2. Thread-Safety Considerations

- **Validator** (`_validate_grounding`): Synchronous, pure function on local data. No shared state. Thread-safe.
- **Storage layer** (`adapter.store_synthesis_*`): Async PostgreSQL driver (likely asyncpg) uses a connection pool; safe for sequential batch calls. We do **not** call storage concurrently; we collect results and store in one batch after all LLM completes.
- **OllamaClient**: Uses aiohttp sessions stored in a dict per host. Designed for concurrent async use. Minor risk: lazy session initialization could race on first use; mitigate by calling `await client.initialize()` at startup or accept negligible race.
- **Assembler & Retriever**: Stateless services; safe for concurrent calls. `assemble_all_sections` is called once before LLM parallelism; it already handles its own concurrency (batch retrieval).
- No other shared mutable state exists across section tasks.

### 3. Baseline Measurement & ≥20% Verification

- **Benchmark suite:** Adapt `scripts/benchmark_suite.py` (Phase 12-01) to use the new parallel synthesis path. The script already times retrieval, synthesis (LLM+validation), and persistence.
- **Key metric:** `sections_per_minute = sections_count / (total_synthesis_ms / 60000)`.
- **Baseline (BASELINE_METRICS.md, HIGH_EVIDENCE):** 8 sections, total synthesis ≈73,394ms → 6.54 sections/min.
- **Target:** ≥7.85 sections/min (20% improvement → total synthesis ≤61.2s for 8 sections).
- **Procedure:** Run ≥10 iterations per scenario, pre/post guardrail pytest, aggregate statistics (mean, median, p95). Compare against baseline.
- The parallelized LLM will reduce wall time from ~52s sequential to ~13s with 4-way concurrency, easily exceeding 20% gain.

### 4. Deterministic Ordering After Parallel Execution

- Each task returns `(section.order, result)`.
- After `asyncio.gather`, build a dict or list and sort by `order` before assembling final report.
- The LLM calls are deterministic (TaskType.SYNTHESIS uses `temperature=0.0` and a fixed seed from `ModelRouter`), so completion order does not affect content.
- Citation keys and `atom_ids_used` order remain unchanged because packets are built before LLM step.

### 5. Hidden Shared State Risks

- **OllamaClient session lazy init:** Possible double-creation of aiohttp sessions if multiple tasks trigger first use simultaneously. Harmless but wasteful. Mitigate by eagerly initializing the client during system startup.
- **Memory pressure:** Concurrent LLM responses buffer multiple large text outputs. Bounded concurrency (4-8) limits this to 2-4× memory increase vs. sequential, which is acceptable.
- **GIL contention:** The validator runs Python string operations; if many tasks finish together, they might contend briefly. Negligible compared to LLM I/O.
- **Event loop blocking:** Avoid any synchronous blocking calls inside tasks (none introduced).

### 6. Process-Based Parallelism vs Threading

Do not use process-based parallelism. LLM inference occurs on a remote Ollama server; our code is I/O-bound waiting for network responses. `asyncio` is optimal: no thread overhead, simple concurrency, and the GIL is released during I/O. Adding threads or processes would complicate error handling and resource management without benefit.

### 7. Individual Section Failure Handling

- Wrap each `process_section` in a retry loop (exponential backoff) for transient errors.
- Use `asyncio.gather(*tasks, return_exceptions=True)` or catch exceptions inside the task and return a sentinel indicating failure.
- On failure (after retries), treat the section as insufficient evidence: store placeholder `"[INSUFFICIENT EVIDENCE FOR SECTION]"` and proceed.
- Log failures with section index for diagnostics.
- The overall report continues; no partial rollback needed because storage is atomic per artifact. If the artifact creation itself fails, that’s a separate error (post-LLM).

### 8. Metrics Instrumentation

- **Per-phase timers** around: plan generation, retrieval (already done), LLM parallel block (wall time), validation (sum of individual), persistence.
- **Counters:** `sections_success`, `sections_failed`, `retries_total`.
- **Throughput:** Compute `sections/min` from total synthesis wall time.
- **Guardrail:** Compare validator rejection rate (should not increase) and ensure `atom_ids_used` integrity (same atom count) vs. baseline.
- For Phase 12-04, these can be exported to structured logs or Prometheus; for now, simple logging is sufficient.

## Recommended Approach

### Code Changes

#### 1. `src/research/archivist/synth_adapter.py`

Modify `write_section` to **ignore** the `previous_context` argument and remove its inclusion from the prompt. Keep the signature for backward compatibility with V2 code paths.

```python
async def write_section(self, packet: EvidencePacket, previous_context: str = "") -> str:
    """Execute the Archivist synthesis constraint on a specific evidence packet."""
    evidence_brief = self._format_evidence_brief(packet)

    prompt = f"""
### SECTION TITLE: {packet.section_title}
### SECTION GOAL: {packet.section_objective}

### EVIDENCE BRIEF (ONLY USE DATA FROM THESE SNIPPETS):
{evidence_brief}

### TASK:
Write this section of the report.
- Integrate the provided evidence using stable Global IDs (e.g. [A1], [S2]).
- IF THE PROVIDED EVIDENCE IS INSUFFICIENT to meet the goal, state: "Specific empirical data for this sub-topic was not found in the primary search phase."
- DO NOT invent "Adversarial Scenarios" or theoretical examples using fake data. Only report real disputes or facts found in the text.
"""
    # Note: Removed "PREVIOUS CONTEXT" and "Maintain logical flow" to enable parallel LLM generation.
    # This does not affect truth contract invariants (per-sentence citation, lexical overlap, contradiction handling).

    logger.info(f"[Archivist] Writing section: '{packet.section_title}' using {len(packet.atoms)} atoms.")
    resp = await self.ollama.complete(
        task=TaskType.SYNTHESIS,
        prompt=prompt,
        system_prompt=SCHOLARLY_ARCHIVIST_PROMPT,
        max_tokens=3000
    )
    return resp
```

Adjust `SCHOLARLY_ARCHIVIST_PROMPT` to remove any wording about "logical flow" if present; current prompt already contains “NO INFERENCE” and per-sentence citation rules, which are preserved.

#### 2. `src/research/reasoning/synthesis_service.py`

Replace the sequential LLM loop with an async worker pool:

```python
# After all_packets obtained from assemble_all_sections():
CONCURRENCY_LIMIT = 8  # could become configurable
sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

async def process_one_section(self, section: SectionPlan, packet: EvidencePacket):
    async with sem:
        if len(packet.atoms) == 0:
            return (section.order, None)
        try:
            prose = await self.archivist.write_section(packet, "")
        except Exception as e:
            logger.error(f"[Synthesis] Section {section.order} LLM error: {e}")
            return (section.order, None)
        if not self._validate_grounding(prose, packet):
            logger.warning(f"[Synthesis] Section {section.order} failed validation")
            return (section.order, None)
        return (section.order, {
            "title": section.title,
            "prose": prose,
            "atom_ids": list(packet.atom_ids_used)
        })

# Build tasks
sorted_plan = sorted(plan, key=lambda s: s.order)
tasks = [asyncio.create_task(self.process_one_section(s, all_packets[s.order]))
         for s in sorted_plan]
task_results = await asyncio.gather(*tasks)  # returns list of (order, data)

# Organize results
sections_to_store = []
citations_to_store = []
full_report = ""
for order, data in sorted(task_results, key=lambda x: x[0]):
    if data is None:
        # Insufficient evidence placeholder
        section_dict = {
            "artifact_id": artifact_id,
            "section_name": f"Section {order}",  # need title; we can also store title from plan
            "section_order": order,
            "summary": "[INSUFFICIENT EVIDENCE FOR SECTION]",
            "mission_id": mission_id,
            "atom_ids_used": []
        }
        sections_to_store.append(section_dict)
        continue
    # Valid section
    section_dict = {
        "artifact_id": artifact_id,
        "section_name": data["title"],
        "section_order": order,
        "summary": data["prose"],
        "mission_id": mission_id,
        "atom_ids_used": data["atom_ids"]
    }
    sections_to_store.append(section_dict)
    for atom_id in data["atom_ids"]:
        citations_to_store.append({
            "artifact_id": artifact_id,
            "section_name": data["title"],
            "atom_id": atom_id,
            "metadata_json": {}
        })
    full_report += f"\n\n## {data['title']}\n{data['prose']}"
```

Retain artifact creation and batch storage (store_synthesis_artifact, store_synthesis_sections, store_synthesis_citations) unchanged.

#### 3. `scripts/benchmark_suite.py`

Adapt the manual synthesis loop to use the same async worker pool pattern to accurately measure wall time. Replace:

```python
previous_context = ""
for section in sorted(plan, key=lambda x: x.order):
    # sequential LLM + validation
```

with the parallel task pattern (adjust to not use `previous_context`). Sum LLM times for diagnostic (each task returns its own duration). The outer `synthesis_total_timer` will then reflect the true parallelized duration.

Example:

```python
# Inside synthesis_total_timer block, after all_packets obtained:
sem = asyncio.Semaphore(8)  # same limit as production
async def llm_task(section, packet):
    async with sem:
        start = time.perf_counter()
        try:
            prose = await archivist.write_section(packet, "")
            elapsed = (time.perf_counter() - start) * 1000
            valid = synthesis_service._validate_grounding(prose, packet)
            return (section.order, section.title, prose, list(packet.atom_ids_used), elapsed, valid)
        except Exception as e:
            logger.error(f"Benchmark LLM error: {e}")
            return (section.order, section.title, None, [], 0, False)

tasks = [asyncio.create_task(llm_task(s, all_packets[s.order])) for s in sorted_plan]
results = await asyncio.gather(*tasks)

sections_data = []
for order, title, prose, atom_ids, llm_ms, valid in sorted(results, key=lambda x: x[0]):
    synthesis_llm_ms_total += llm_ms
    if prose is None or not valid:
        prose = "[INSUFFICIENT EVIDENCE FOR SECTION]"
    sections_data.append({...})
    # build full_report as before
```

This ensures the benchmark mirrors production changes and reports accurate throughput.

## Implementation Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| OOM from buffered LLM outputs | High (if concurrency too high) | Choose conservative default (4-8), monitor memory; provide env override |
| OllamaClient session lazy-init race | Low (duplicate sessions) | Eagerly initialize client at system startup; minor resource waste otherwise acceptable |
| Loss of report narrative flow | Medium (quality) | Not a truth contract violation; acceptable trade-off for performance. If needed, could be revisited in future quality phases. |
| Validation GIL contention | Low | Validation is <1ms; even with bursts negligible |
| Storage concurrency not exercised | None | We store in single batch; no concurrency needed |
| Third-party LLM service timeout under load | High (failed sections) | Implement retry with backoff; acceptable to mark insufficient if retries exhausted |
| Benchmark no longer reflects same breakdown | Medium | Update benchmark inline with production code; keep per-section timing inside tasks |

## Metrics & Verification

- **Primary success metric:** `sections_per_minute` measured by benchmark. Must show ≥20% improvement over baseline (6.54 → 7.85+).
- **Guardrail metrics:**
  - Validator rejection rate unchanged (baseline had 0% pass? Actually all failed due to missing citations; but we care about rate stability).
  - `atom_ids_used` integrity: sum of atom counts across sections should match before/after.
  - Determinism: Same seed and corpus produce identical output bytes (spot-check).
- **Process:**
  1. Ensure guardrail pytest passes (v1.0 tests + Phase 11 invariants).
  2. Run benchmark with ≥10 iterations for both no_discovery and high_evidence.
  3. Compare aggregates against `BASELINE_METRICS.md`.
  4. Confirm regression only in positive direction (faster) without correctness loss.
- **Failure criteria:** If any guardrail test fails or `atom_ids_used` mismatches, the implementation is incorrect.

## References

- **Phase context:** `.planning/phases/12-03/12-03-CONTEXT.md` (decisions & constraints)
- **Baseline metrics:** `BASELINE_METRICS.md`
- **Current synthesis service:** `src/research/reasoning/synthesis_service.py`
- **Archivist adapter:** `src/research/archivist/synth_adapter.py`
- **Evidence assembler (retrieval pattern):** `src/research/reasoning/assembler.py`
- **V3 retriever (existing concurrency):** `src/research/reasoning/v3_retriever.py`
- **Benchmark suite:** `scripts/benchmark_suite.py`
- **LLM client (async safe):** `src/llm/client.py`
- **Truth contract invariants:** `.planning/phases/11-reports/PHASE-11-CONTEXT.md`
- **Tests to verify:** `tests/research/reasoning/test_phase11_invariants.py`
