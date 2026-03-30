# PHASE 11.1 — REPORT PIPELINE HARDENING: CONTEXT

**Purpose:** Provide the failure context from Phase 11 that this hardening phase addresses.

---

## Phase 11 Audit Summary (Blocking Failures)

| # | Failure | Locked Decision Violated |
|---|---------|---------------------------|
| 1 | HybridRetriever used instead of V3Retriever | Decision 1: V3Retriever ONLY |
| 2 | No `atom_ids_used` storage → lineage broken | Decision 5: Store atom IDs per section |
| 3 | No `mission_id` binding → identity leak | Decision 6: mission_id canonical |
| 4 | Transformation-only not enforced → inference allowed | Decision 9: Zero inference |
| 5 | "MINIMUM 1000 WORDS" in prompt → hallucination pressure | Decision 4: Remove word count minimum |
| 6 | No deterministic sampling → regeneration fails | Regeneration requirement |
| 7 | Insufficient evidence handling incorrect → writes with empty atoms | Decision 2: Binary refusal |

**Contradiction handling:** Partial — mechanism exists but conditional; not a blocking failure but must verify.

---

## Truth Contract Reference

From Phase 10 and Phase 11 Context:

- **Grounded answers only:** Every factual claim must map directly to a retrieved atom.
- **No inference:** Cannot fill gaps, combine atoms to create new conclusions, or extrapolate.
- **Binary coverage:** All material claims must have at least one supporting citation; otherwise, section `[INSUFFICIENT EVIDENCE]`.
- **Mandatory retrieval:** All evidence must come from `V3Retriever`.
- **Contradictions preserved:** Conflicting atoms must appear and be acknowledged.
- **Report = pure transformation:** zero inference, no new facts.

---

## Current Code State (Pre-Hardening)

### Retrieval Path
```python
# assembler.py
from src.retrieval.retriever import HybridRetriever  # ← WRONG
class EvidenceAssembler:
    def __init__(..., retriever: HybridRetriever, ...):
        self.retriever = retriever
```

### Provenance
```python
# EvidencePacket lacks atom_ids_used
@dataclass
class EvidencePacket:
    atoms: List[Dict]  # contains atoms but no separate ID list

# Storage only inline_text
await adapter.store_synthesis_section({
    "inline_text": prose,
    # MISSING: "atom_ids_used": [...]
})
```

### Mission Binding
No `mission_id` in any synthesis function signature. Only `topic_id` used.

### Prompt
```text
MINIMUM 1000 WORDS.
```
and no explicit per-sentence citation rule or no-inference constraint.

### Generator
```python
resp = await ollama.complete(...)  # no temperature=0, no seed
```

### Insufficient Evidence
```python
if not packet.atoms:
    console.print("[yellow]  - Warning: Minimal evidence...[/yellow]")
# Still calls archivist.write_section()
```

---

## Required Invariants (Post-Hardening)

See PLAN.md for full invariant specifications. In brief:

1. **V3Retriever ONLY**
2. **atom_ids_used captured and stored**
3. **mission_id propagates to all queries**
4. **Transformation-only: per-sentence citation, no inference**
5. **Grounding validator enforces citation presence + support**
6. **Deterministic: temperature=0, fixed seed, sorted atoms**
7. **Binary refusal: insufficient evidence → skip section**

---

## DB Schema Changes

The `authority.synthesis_citations` table already exists and is designed to store atom-level provenance:

```sql
CREATE TABLE authority.synthesis_citations (
    citation_id BIGSERIAL PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES authority.synthesis_artifacts(artifact_id) ON DELETE CASCADE,
    section_name TEXT,
    atom_id TEXT REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE SET NULL,
    source_id TEXT REFERENCES corpus.sources(source_id) ON DELETE SET NULL,
    citation_label TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

**Required:** After storing synthesis sections, also insert citations by calling `adapter.store_synthesis_citations()` with one row per atom used in each section. No schema changes needed.

If `mission_id` is not present on `synthesis_artifacts` or `synthesis_sections`, add:

```sql
ALTER TABLE authority.synthesis_artifacts
ADD COLUMN mission_id UUID REFERENCES missions(id);
-- Backfill from topic→mission lookup if needed
```

Verify whether `synthesis_sections` needs `mission_id` as well (likely inherited from artifact).

---

## Testing Requirements

For each invariant, write a unit test that:

- Sets up a mock evidence packet with known atoms
- Calls the synthesis component
- Asserts the invariant holds (e.g., validator passes/fails correctly, DB stores atom list, query includes mission_id)

Tests should cover both compliant and non-compliant inputs to ensure enforcement.

---

## Success Criteria

Re-run Phase 11 audit after hardening. Expected outcome:

- **All 7 blocking failures resolved** → PASS or PARTIAL (non-blocking only)
- No new failures introduced
- Unit tests green

---

**This phase is the remediation for Phase 11 FAIL.** Proceed with implementation.
