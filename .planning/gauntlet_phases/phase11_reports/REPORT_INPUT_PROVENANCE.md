# PHASE 11 — REPORT GENERATION AUDIT
## Deliverable: REPORT_INPUT_PROVENANCE.md

**Auditor:** Claude Code
**Date:** 2026-03-29

---

## Purpose

Verify that report inputs come from **V3Retriever** (only stored atoms) and that **atom ID lists** are captured for provenance.

---

## Findings

### 1. Retrieval Source Compliance

#### Expected (Locked Decision #1)
> **V3Retriever ONLY** for evidence gathering

#### Actual Implementation

File: `src/research/reasoning/assembler.py:37`

```python
class EvidenceAssembler:
    def __init__(self, ollama: OllamaClient, memory: MemoryManager, retriever: HybridRetriever, adapter=None):
        self.retriever = retriever  # ← receives HybridRetriever
```

File: `src/research/reasoning/assembler.py:105`

```python
retrieved_context = await self.retriever.retrieve(q)  # uses whatever retriever was injected
```

**Status:** **NON-COMPLIANT**

The assembler accepts a `HybridRetriever` and uses it to fetch evidence. No V3Retriever integration exists in the codebase for the synthesis path.

**Note:** `V3Retriever` class exists in `src/research/reasoning/v3_retriever.py`, but it is **not used** by `SynthesisService` or `EvidenceAssembler`. There is no wiring to swap it in.

**Conclusion:** Reports would **not** use stored atoms only — they would use `HybridRetriever`, which (based on its name) likely combines multiple retrieval strategies and may not enforce V3 truth contract constraints.

---

### 2. Atom ID Capture

#### Expected (Locked Decision #5)
> Store `atom_ids_used` per section for regeneration provenance

#### Actual Implementation

`EvidencePacket` dataclass (`assembler.py:29-34`):

```python
@dataclass
class EvidencePacket:
    topic_name: str
    section_title: str
    section_objective: str
    atoms: List[Dict] = field(default_factory=list)
    contradictions: List[Dict] = field(default_factory=list)
    # NO atom_ids_used field
```

Each atom dict in `packet.atoms` contains:

```python
{
    "global_id": "[A###]",    # citation key string
    "text": "...",
    "type": "...",
    "metadata": {"source": ...}
}
```

The evidence packet **does not store atom IDs** in a separate, machine-parseable list. It stores `global_id` (citation key) as a string within the atom dict, but there is no top-level `atom_ids_used: List[str]` field that lists IDs in order of citation.

#### Storage to Database

`SynthesisService.generate_master_brief()` (`synthesis_service.py:69-75`):

```python
await self.adapter.store_synthesis_section({
    "artifact_id": artifact_id,
    "section_name": section.title,
    "section_order": section.order,
    "inline_text": prose
})
```

**Missing:** `atom_ids_used` is not passed to or stored by the adapter.

**Conclusion:** Atom IDs are **not captured** in the synthesis artifact. Provenance cannot be reconstructed from Postgres alone.

---

### 3. Mission ID Binding

#### Expected (Locked Decision #6)
> `mission_id` is canonical — all report artifacts bound to `mission_id`

#### Actual Implementation

Call chain analysis:

| Function | Parameters | Mission ID Used? |
|----------|------------|------------------|
| `generate_master_brief(topic_id)` | `topic_id: str` | ✗ No mission_id |
| `build_evidence_packet(topic_id, ...)` | `topic_id: str` | ✗ No mission_id |
| `V3Retriever.retrieve(query)` | `query.topic_filter` | Would need mission_id (unknown) |
| Database queries | `WHERE topic_id =` | ✗ Filtering by topic only |

**No `mission_id` appears anywhere** in the synthesis code.

**Conclusion:** Reports are **not** bound to mission identity. This violates the V3 identity model and breaks mission-scoped isolation.

---

### 4. Provenance Chain Summary

```
[ user request ]
      ↓
generate_master_brief(topic_id)
      ↓
EvidenceAssembler.build_evidence_packet(topic_id)
      ↓
HybridRetriever.retrieve() — ❌ wrong retriever
      ↓
EvidencePacket(atoms) — ❌ no atom_ids_used field
      ↓
Archivist writes prose (with citations embedded in text)
      ↓
store_synthesis_section(inline_text) — ❌ no atom list stored
```

**Result:** Even if we overlook the `HybridRetriever` violation, the **provenance chain is broken** because:

- Atom IDs are not extracted and persisted
- No machine-readable mapping from report sentences to atoms
- Cannot verify that every claim maps to an atom

---

## Verdict Markers

| Requirement | Pass? | Evidence |
|-------------|-------|----------|
| Uses V3Retriever | ✗ | `assembler.py:37` uses `HybridRetriever` |
| Atom IDs stored per section | ✗ | `synthesis_service.py:69-75` stores only `inline_text` |
| Mission ID binding | ✗ | No `mission_id` in any parameter or query |
| Evidence packet includes raw atoms | ✓ | `packet.atoms` contains atom dicts (but from wrong source) |

---

**Wave 1 Checkpoint:** Ready for user review. Proceed to Wave 2 (evidence carry-through + final verification)?
