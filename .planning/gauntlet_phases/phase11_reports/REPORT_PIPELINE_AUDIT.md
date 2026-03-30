# PHASE 11 — REPORT GENERATION AUDIT
## Deliverable: REPORT_PIPELINE_AUDIT.md

**Auditor:** Claude Code
**Date:** 2026-03-29
**Phase:** 11 — Report Generation Audit

---

## Executive Summary

The report generation pipeline (`SynthesisService.generate_master_brief()`) has been inspected end-to-end. **Critical compliance failures** are identified across all truth contract dimensions. The synthesis code path is currently **disabled** in production (`SystemManager.synthesis_service = None`), but the audit examines the implementation to determine whether it would comply if enabled.

**Overall Verdict:** FAIL (if enabled) / NON-COMPLIANT (inactive path)

---

## 1. Pipeline Architecture Map

```
generate_master_brief(topic_id)
    │
    ├─► generate_section_plan(topic_name) → LLM (Architect)
    │       └─► Returns: List[SectionPlan]
    │
    └─► For each section:
            │
            ├─► build_evidence_packet(topic_id, topic_name, section)
            │       │
            │       ├─► HybridRetriever.retrieve(RetrievalQuery) ❌ V3Retriever violation
            │       ├─► Deduplicate atoms
            │       ├─► get_unresolved_contradictions(topic_id) ✓
            │       └─► Returns: EvidencePacket(atoms, contradictions)
            │
            ├─► archivist.write_section(packet, previous_context)
            │       │
            │       ├─► Format evidence brief with [A###] citation keys
            │       ├─► Inject "MINIMUM 1000 WORDS" ❌ Hallucination pressure
            │       ├─► Call ollama.complete() ❌ No sampling control
            │       └─► Returns: prose string
            │
            └─► store_synthesis_section(artifact_id, section, prose)
                    └─► Stores inline_text only ❌ No atom_ids_used
```

---

## 2. Data Flow Inspection

### 2.1 Input Sources

| Component | Source | Compliance |
|-----------|--------|------------|
| `EvidenceAssembler` | `HybridRetriever` (constructor arg) | **FAIL** — must be V3Retriever |
| `EvidenceAssembler` | `MemoryManager.get_unresolved_contradictions()` | ✓ OK — Postgres query |
| `SynthesisService` | `topic_id` parameter only | **FAIL** — no mission_id propagation |
| `ArchivistSynthAdapter` | `EvidencePacket.atoms` (from assembler) | ✓ OK — but atoms are from wrong retriever |

**Violation:** Locked Decision #1 mandates **V3Retriever ONLY**. Current code uses `HybridRetriever` (imported `src.retrieval.retriever.HybridRetriever`) and passes it to `EvidenceAssembler.__init__`.

### 2.2 Retrieval Mechanism

File: `src/research/reasoning/assembler.py:92-105`

```python
async def build_evidence_packet(self, topic_id: str, topic_name: str, section: SectionPlan) -> EvidencePacket:
    ...
    retrieved_context = await self.retriever.retrieve(q)  # uses self.retriever (HybridRetriever)
```

The retriever is injected at assembler construction, not instantiated inside. This means even if V3Retriever exists, it is **not wired** into the synthesis pipeline.

**Hard fail:** Uses `HybridRetriever`, not V3Retriever.

### 2.3 Citation Assignment

Citations appear to be taken from `RetrievedItem.citation_key`:

```python
packet.atoms.append({
    "global_id": f"[{item.citation_key}]" if item.citation_key else f"[A{len(seen_ids)}]",
    ...
})
```

**Issue:** Citation keys depend on `citation_key` being populated during atom ingestion (Phase 09 responsibility). This is acceptable **if** Phase 09 consistently populates that field. The audit cannot verify that without inspecting ingestion code, but the mechanism is present.

**Status:** STRUCTurally sound, but correctness depends on upstream data quality.

### 2.4 Provenance Recording

File: `src/research/reasoning/synthesis_service.py:69-75`

```python
if self.adapter:
    await self.adapter.store_synthesis_section({
        "artifact_id": artifact_id,
        "section_name": section.title,
        "section_order": section.order,
        "inline_text": prose
    })
```

**Missing:** `atom_ids_used` list. Only `inline_text` is stored.

**Violation:** Locked Decision #5 requires storing `atom_ids_used` for each section. Not implemented. Database schema likely lacks this column.

---

## 3. Prompt Compliance Audit

File: `src/research/archivist/synth_adapter.py:51-69`

### 3.1 Grounding Constraints

**Present:**
- "ONLY USE DATA FROM THESE SNIPPETS"
- "Integrate the provided evidence using stable Global IDs"
- "DO NOT invent Adversarial Scenarios or theoretical examples using fake data"

**Missing:**
- Explicit "Use ONLY the provided evidence. Do NOT use your general training" — Phase 10 style
- No temperature=0 or fixed seed requirement
- No verification that LLM adhered to citations

**Assessment:** Prompt attempts grounding but is **not as rigorous** as Phase 10 retrieval contract. The wording "ONLY USE DATA FROM THESE SNIPPETS" is weaker than "You must not use internal knowledge."

### 3.2 Hallucination Pressure

**Line 68:** `MINIMUM 1000 WORDS.`

**Violation:** Locked Decision #4 — "Remove 'minimum word count' from synthesis prompts." Present and creates pressure to generate content even when evidence is sparse.

### 3.3 Insufficient Evidence Handling

Prompt text (line 65):

```
IF THE PROVIDED EVIDENCE IS INSUFFICIENT to meet the goal, state:
"Specific empirical data for this sub-topic was not found in the primary search phase."
```

**Present:** ✓ Insufficient evidence rule is defined.

**Critical gap:** The decision to skip writing a section is made in `SynthesisService`, not in the Archivist. Code at `synthesis_service.py:61-64`:

```python
if not packet.atoms:
    console.print("[yellow]  - Warning: Minimal evidence found for this section.[/yellow]")
```

It **still calls** `archivist.write_section()` even when `packet.atoms` is empty. The Archivist then may produce speculative prose despite the "state insufficiency" instruction.

**Violation:** Locked Decision #2 — "Binary refusal for insufficient evidence — do not write sections lacking atoms." The code does **not** skip writing; it writes anyway with a warning.

---

## 4. Identity Binding Audit

Search for `mission_id` in synthesis code:

- `synthesis_service.py`: references `topic_id` only (lines 26, 32, 48, 59, etc.)
- `assembler.py`: uses `topic_id` (lines 92, 102, 123)
- `synth_adapter.py`: no mission_id at all

**Missing:** No `mission_id` anywhere in the synthesis call chain.

**Violation:** Locked Decision #6 — "mission_id is canonical — bind all report artifacts to mission_id."

Current code uses bare `topic_id`, which breaks mission-scoped report isolation.

---

## 5. Contradiction Handling

Component: `EvidenceAssembler.build_evidence_packet()` (lines 121-129)

```python
if "contradictions" in [r.lower() for r in section.target_evidence_roles] or "risks" in section.title.lower():
    conflicts = await self.memory.get_unresolved_contradictions(topic_id, limit=5)
    packet.contradictions.append(...)
```

**Mechanism:**
- Contradictions only pulled if section targets "contradictions" role OR title contains "risks"
- Contradictions come from `MemoryManager.get_unresolved_contradictions()` — Postgres query
- Packaged into `EvidencePacket.contradictions`

**Archivist prompt** (line 40-43):

```
### IDENTIFIED CONTRADICTIONS IN EVIDENCE:
- CONFLICT: ...
  CLAIM A: ...
  CLAIM B: ...
```

**Assessment:** ✓ Structure exists to surface contradictions. However:
- Unclear whether `get_unresolved_contradictions` is implemented and returns data
- Unclear if V3Retriever integration would affect contradiction retrieval (should not, it's separate)

**Status:** STRUCTURE PRESENT but implementation completeness unknown.

---

## 6. Transformation-Only Enforcement

**Core question:** Does report synthesis introduce new claims not present in atoms?

### 6.1 Evidence Completeness

`HybridRetriever.retrieve()` returns `RetrievedItem` objects. The assembler extracts `item.content` and `item.metadata`.

**Concern:** Is there any filtering applied post-retrieval? No — all items are added to `packet.atoms` (deduplicated only by ID). So the **full retrieved set** is passed to the Archivist.

**✓ OK:** Evidence completeness appears intact (assuming retriever returns everything).

### 6.2 LLM Inference Leeway

Prompt does **not** explicitly forbid:
- Combining multiple atoms to infer a new conclusion
- Summarizing across atoms to create synthesized claims
- Resolving contradictions (it says "explicitly state the disagreement" — good)

**Example of potential leakage:**
If atoms say:
- A: "The reactor operates at 300°C"
- B: "The reactor operates at 350°C"

Archivist could write: "The reactor operates between 300°C and 350°C" — this **invents** an intermediate range not directly stated.

The prompt does not forbid this.

**Assessment:** ❌ **Transformation-only enforcement is NOT strict enough.** The prompt needs explicit: "Do not combine, infer, or interpolate between claims. Only report what each source states individually."

---

## 7. Regeneration Capability

### 7.1 Determinism

`ArchivistSynthAdapter.write_section()` calls:

```python
resp = await self.ollama.complete(
    task=TaskType.SYNTHESIS,
    prompt=prompt,
    system_prompt=SCHOLARLY_ARCHIVIST_PROMPT,
    max_tokens=3000
)
```

**Missing:** No `temperature` or `seed` parameters passed. Default LLM sampling will be non-deterministic.

**Violation:** Phase 11 verification requires "Regeneration possible from Postgres only" with deterministic output. Without fixed seed/temperature=0, identical atoms can produce different prose on different runs.

### 7.2 Reconstruction from Atoms

Theoretically possible if:
- `atom_ids_used` were stored (currently not)
- Prompt is strict enough to prevent LLM variation from changing meaning even if prose differs
- The same LLM model and parameters are used

**Current status:** ✗ Not achievable because `atom_ids_used` is not stored, making lineage unverifiable.

---

## 8. Synthesis Service Activation Status

Per `PHASE-11-CONTEXT.md`:

> `SynthesisService` is currently disabled in `SystemManager` (`self.synthesis_service = None`).

**Implication:** The code path is **untested in production**. Any audit findings are based on static code inspection, not observed behavior.

This increases risk: implementation may deviate from expectations when enabled.

---

## 9. Hard Fail Conditions Assessment

| Hard Fail Condition | Status | Evidence |
|--------------------|--------|----------|
| Reports detached from lineage | **FAIL** (would) | `atom_ids_used` not stored; no deterministic binding |
| Reports depend on fresh browsing | ✓ PASS | No web queries in synthesis code |
| Reports synthesized from vague summaries | **FAIL** (would) | Uses word count pressure; allows inference; not strict transformation-only |

---

## 10. Deliverable Map

This audit report maps to the required deliverables:

| Deliverable | Source Section | Status |
|-------------|----------------|--------|
| `REPORT_PIPELINE_AUDIT.md` | this document | ✓ |
| `REPORT_INPUT_PROVENANCE.md` | Sections 1–2, 4 | See below |
| `REPORT_EVIDENCE_CARRYTHROUGH.md` | Sections 6, 7 | See below |
| `PHASE-11-VERIFICATION.md` | Section 9 + consolidated | See below |

The following two deliverables (`REPORT_INPUT_PROVENANCE.md`, `REPORT_EVIDENCE_CARRYTHROUGH.md`) are produced as separate files to match the gauntlet requirements.

---

**Wave 1 Completed** — Pending user review before Wave 2 (report compilation and final verification).
