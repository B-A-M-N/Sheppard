# Instrumentation Guidance for Phase 12-01

**Target:** Implement `scripts/benchmark_suite.py` with fine-grained timing and evidence shape metrics.

## Architecture Overview

The V3 pipeline components live under `src/`:

- **System Orchestration**: `src/core/system.py` → `SystemManager`
  - `system_manager.learn()` starts a mission and begins acquisition/condensation
  - `system_manager.generate_report(mission_id)` triggers synthesis (retrieval + synthesis + validation + persistence)

- **Acquisition**: `src/research/acquisition/`
  - Frontier & crawling handled by `FirecrawlLocalClient` and `AdaptiveFrontier`
  - Ingestion triggers condensation automatically via callback

- **Condensation**: `src/research/condensation/pipeline.py` → `DistillationPipeline`
  - Called via `_condensation_callback` during ingestion

- **Retrieval**: `src/research/reasoning/v3_retriever.py` → `V3Retriever`
  - `retriever.retrieve(query: RetrievalQuery) -> RoleBasedContext`
  - Queries Chroma `knowledge_atoms` collection

- **Evidence Assembly**: `src/research/reasoning/assembler.py` → `EvidenceAssembler`
  - `assembler.generate_section_plan(topic_name)` → `List[SectionPlan]`
  - `assembler.build_evidence_packet(mission_id, topic_name, section)` → `EvidencePacket`
    - Internally calls `retriever.retrieve()`

- **Synthesis (LLM)**: `src/research/archivist/synth_adapter.py` → `ArchivistSynthAdapter`
  - `archivist.write_section(packet, previous_context) -> str`
  - Calls `ollama.complete()` with SYNTHESIS task

- **Validator**: `src/research/reasoning/synthesis_service.py` → `SynthesisService._validate_grounding()`
  - Private method called per-section after prose generation
  - Validates per-sentence citation and lexical overlap

- **Persistence**: `src/memory/storage_adapter.py` → `SheppardStorageAdapter`
  - `adapter.store_synthesis_artifact(artifact)`
  - `adapter.store_synthesis_sections(sections)`
  - `adapter.store_synthesis_citations(citations)`
  - Called from `SynthesisService.generate_master_brief()`

## Benchmark Scenarios

### NO_DISCOVERY
- Mission yields zero atoms (e.g., obscure query or short ceiling with no results).
- Expected: retrieval returns empty; synthesis marks sections insufficient or short-circuits.

### HIGH_EVIDENCE
- Mission yields multiple atoms and triggers full synthesis.
- Follow `scripts/run_e2e_mission.py` pattern (topic: "Python programming language", ceiling_gb=0.001).
- Must validate: atom_count >= sections_count on average.

## Instrumentation Points

To achieve the required breakdown without modifying production code, wrap these calls with `time.perf_counter()`:

1. **Frontier & Acquisition**: Time the `system_manager.learn()` → wait for mission completion.
   - Call `await wait_for_mission_completion(adapter, mission_id, timeout)` similar to e2e script.
   - This encompasses frontier, crawling, and ingestion.

2. **Condensation**: Not directly exposed as a single call; occurs incrementally via callback during acquisition.
   - **Option A**: Sum time spent in `condenser.run()` via monkey-patch (advanced).
   - **Option B**: Omit separate condensation timing and let "frontier_acquisition" cover ingestion+condensation as a single stage (verify with user if acceptable).
   - **Option C**: Use existing logging/metrics if available (Phase 12-04 will add this).

3. **Retrieval**: Directly call `retriever.retrieve(query)` for each section during synthesis.
   - To isolate, we can patch `EvidenceAssembler.build_evidence_packet()` to time the retrieval calls it makes.
   - Or re-run retrieval separately after mission completion: for each section plan, call `retriever.retrieve()` with appropriate query.

4. **Synthesis LLM**: Time `archivist.write_section(packet, previous_context)` for each section.

5. **Validator**: Time `_validate_grounding(prose, packet)` for each section.
   - This is a `SynthesisService` private method; can be called directly if we have an instance.
   - We can create a `SynthesisService` instance with the same assembler/adapter from system_manager.

6. **Persistence**: Time `adapter.store_synthesis_artifact()`, `store_synthesis_sections()`, `store_synthesis_citations()` around the final storage block.

## Suggested Benchmark Structure

```python
import asyncio, time, json
from core.system import system_manager

async def time_synthesis_components(mission_id, adapter, assembler, archivist, synthesis_service):
    """Break down synthesis into retrieval, LLM, validator, persistence."""
    # 1. Generate section plan
    plan_start = time.perf_counter()
    plan = await assembler.generate_section_plan(topic_name)  # need topic_name from mission
    plan_end = time.perf_counter()
    section_plan_ms = (plan_end - plan_start) * 1000

    retrieval_ms_total = 0
    synthesis_llm_ms_total = 0
    validator_ms_total = 0
    sections = []
    all_atom_ids = []
    call_counts = {"retrieval_queries": 0, "validator_invocations": 0}

    previous_context = ""
    for section in sorted(plan, key=lambda x: x.order):
        # 2. Build evidence packet (includes retrieval)
        packet_start = time.perf_counter()
        packet = await assembler.build_evidence_packet(mission_id, topic_name, section)
        packet_end = time.perf_counter()
        # The build_evidence_packet likely calls retriever.retrieve(). We can attribute that time to retrieval.
        retrieval_ms_total += (packet_end - packet_start) * 1000
        call_counts["retrieval_queries"] += 1

        # 3. Write section if atoms exist
        if len(packet.atoms) == 0:
            prose = "[INSUFFICIENT EVIDENCE FOR SECTION]"
        else:
            llm_start = time.perf_counter()
            prose = await archivist.write_section(packet, previous_context)
            llm_end = time.perf_counter()
            synthesis_llm_ms_total += (llm_end - llm_start) * 1000

            # 4. Validate grounding
            val_start = time.perf_counter()
            valid = synthesis_service._validate_grounding(prose, packet)
            val_end = time.perf_counter()
            validator_ms_total += (val_end - val_start) * 1000
            call_counts["validator_invocations"] += 1
            if not valid:
                prose = "[INSUFFICIENT EVIDENCE FOR SECTION]"

        sections.append({
            "order": section.order,
            "title": section.title,
            "prose": prose,
            "atom_count": len(packet.atoms),
            "atom_ids": list(packet.atom_ids_used)
        })
        all_atom_ids.extend(packet.atom_ids_used)
        previous_context += f"\n\n## {section.title}\n{prose}"

    # 5. Persistence
    persist_start = time.perf_counter()
    # Need to create artifact and store sections/citations as in generate_master_brief
    # Reuse that logic but time just the adapter.store_* calls
    persist_end = time.perf_counter()
    persistence_ms = (persist_end - persist_start) * 1000

    total_synthesis_ms = section_plan_ms + retrieval_ms_total + synthesis_llm_ms_total + validator_ms_total + persistence_ms

    return {
        "total_synthesis_ms": total_synthesis_ms,
        "section_plan_ms": section_plan_ms,
        "retrieval_ms": retrieval_ms_total,
        "synthesis_llm_ms": synthesis_llm_ms_total,
        "validator_ms": validator_ms_total,
        "persistence_ms": persistence_ms,
        "sections": sections,
        "atom_count": len(set(all_atom_ids)),
        "call_counts": call_counts
    }
```

## Evidence Shape Metrics

From the returned `sections` list, compute:
- `sections_count` = number of sections (plan length)
- `atom_count` = unique atom IDs used across all sections
- `avg_atoms_per_section` = atom_count / sections_count (mean)
- `chunk_count` → requires counting chunks that contributed atoms; may need to query adapter: for each atom_id, get its source chunk.

If chunk_count is too expensive, omit or approximate.

## NO_DISCOVERY Path

If retrieval returns no atoms, synthesis may:
- Still call `generate_section_plan` (LLM call)
- Then for each section, `build_evidence_packet` returns zero atoms → skip LLM and validator
- Store sections with insufficient evidence placeholder

Timing for NO_DISCOVERY should still capture section planning and any retrieval attempts.

## Guardrail Verification

Before and after benchmarks, run:
```bash
pytest tests/ -q  # or specific v1.0 tests
```
Ensure exit code 0. If fails, abort benchmarks.

## Output JSON Structure

Follow the PLAN.md spec. Include both NO_DISCOVERY and HIGH_EVIDENCE runs in a single file or separate files.

## Accessing Components

After `await system_manager.initialize()`:
- `adapter = system_manager.adapter`
- `retriever = system_manager.retriever`
- `assembler = system_manager.synthesis_service.assembler`
- `archivist = system_manager.synthesis_service.archivist`
- `synthesis_service = system_manager.synthesis_service`

Use these directly; they're already initialized.

## Useful Imports

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
```

## Database Config

Use same approach as `run_e2e_mission.py` to override DB URL if needed:
```python
from src.config.database import DatabaseConfig
DatabaseConfig.DB_URLS["sheppard_v3"] = "postgresql://sheppard:1234@localhost:5432/sheppard_v3"
```

## Cleanup

After each iteration, consider:
- Deleting the mission to avoid DB bloat: `await adapter.delete_mission(mission_id)` if such method exists, or run a cleanup script.
- Or use a dedicated test database and wipe between runs.

---

**Next**: Implement `scripts/benchmark_suite.py` following this guidance. Ensure it's executable (`#!/usr/bin/env python3`) and has `--scenario`, `--iterations`, `--output` args.
