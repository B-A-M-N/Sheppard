# PHASE 11 — REPORT GENERATION AUDIT
## Deliverable: REPORT_EVIDENCE_CARRYTHROUGH.md

**Auditor:** Claude Code
**Date:** 2026-03-29

---

## Purpose

Demonstrate whether **every sentence** in the generated report can be traced back to a specific atom ID (1:1 mapping).

---

## Mechanism Under Audit

The intended carry-through flow:

1. `V3Retriever.retrieve()` returns `RetrievedItem` objects, each with:
   - `content` (atom text)
   - `citation_key` (e.g., `[A001]`)
   - `metadata` (including atom `id` in database)

2. `EvidenceAssembler.build_evidence_packet()` builds `packet.atoms`:

```python
packet.atoms.append({
    "global_id": f"[{item.citation_key}]",  # e.g., "[A001]"
    "text": item.content,
    ...
})
```

3. `ArchivistSynthAdapter.write_section()` receives the packet and formats an evidence brief:

```python
for atom in packet.atoms:
    brief += f"{atom.get('global_id')} TYPE: ...\nCONTENT: {atom.get('text')}\n\n"
```

4. Archivist prompt instructs:

```
Integrate the provided evidence using stable Global IDs (e.g. [A1], [S2]).
```

5. LLM is expected to include citations like `[A1]` inline in the prose.

6. (Missing) `atom_ids_used` list should be stored to map prose citations back to exact atom IDs.

---

## Why Carry-Through Currently Fails

### Failure 1: Wrong Retriever → Wrong Atom Source

Using `HybridRetriever` instead of `V3Retriever` means:

- Atoms may come from non-V3 sources (e.g., in-memory cache, chunks, summaries)
- The `citation_key` attached may not correspond to a `knowledge.knowledge_atoms.id`
- Lineage traceability to the canonical atom store is broken

**Result:** Even if citations are present, they may not map to **stored atoms** in Postgres.

---

### Failure 2: No Structured Atom ID List

The code **does not** create a mapping:

```json
{
  "section_title": "...",
  "prose_sentence_1": "[A001]",
  "prose_sentence_2": "[A001][A003]",
  ...
}
```

Instead, `atom_ids_used` is **not stored at all**. The only persistence is `inline_text` (the full prose with citations embedded as strings).

**Verification impossible:** There is no database artifact that says "sentence X cites atom Y." The only evidence would be human reading of `inline_text` to extract the `[A###]` tokens and match them to the evidence packet. This is:

- Not programmatic
- Not deterministic
- Not suitable for automated regeneration checks

---

### Failure 3: Word Count Pressure → Hallucinated Content

Prompt includes `MINIMUM 1000 WORDS.` This creates incentive to:

- Reiterate points
- Elaborate beyond the atoms
- Insert filler that may not be directly cited

If the LLM writes 1000 words but only 400 words are directly covered by atoms, the remaining 600 words may be paraphrasing, inference, or speculation.

**Result:** Not every sentence maps to an atom; some sentences are **unmarked** (no citation).

---

### Failure 4: Inference Not Explicitly Forbidden

The prompt does NOT say:

> "Each sentence must include at least one citation. Do not make claims not directly supported by a cited source."

It says:

> "Integrate the provided evidence using stable Global IDs."

This allows the LLM to write uncited general statements that are **technically** within the section's topic but **not** traceable to any atom.

**Example:**

Evidence packet contains:
- `[A1]` "France invaded Algeria in 1830."
- `[A2]` "Algerian resistance lasted until 1847."

LLM might write (without citation):

> "The French conquest of Algeria was a prolonged military campaign."

This sentence **paraphrases** the two atoms but does not cite either. It is a **new claim** (adds characterization "prolonged") not directly in any atom. It would fail the 1:1 sentence-to-atom test.

---

### Failure 5: No Verification Pass in Code

There is **no post-generation validator** that:

- Parses `inline_text` to extract all `[A###]` citations
- Confirms every citation key corresponds to an atom in `packet.atoms`
- Ensures every sentence has at least one citation
- Rejects the output if violations are found

The output is accepted as-is and stored. No integrity gate exists.

---

## What Would a Working Implementation Look Like?

### 1. Strict Citation Requirement

Prompt addition:

```
CONSTRAINT: Every declarative sentence in this section MUST be followed by a citation in [A###] format.
If you cannot cite a specific source for a claim, do not include it.
```

### 2. Post-Write Validation

After `write_section()` returns:

```python
atoms_cited = set(packet.atoms_by_citation.keys())
citations_found = extract_all_citations(prose)  # regex findall r'\[A\d+\]'

missing = citations_found - atoms_cited
if missing:
    raise ValidationError(f"Citations not in evidence packet: {missing}")

uncited_sentences = split_sentences_without_citations(prose)
if uncited_sentences:
    raise ValidationError(f"Sentences lacking citations: {len(uncited_sentences)}")
```

### 3. Atom ID List Storage

```python
await adapter.store_synthesis_section({
    "artifact_id": artifact_id,
    "section_name": section.title,
    "section_order": section.order,
    "inline_text": prose,
    "atom_ids_used": list(citations_in_order)  # e.g., ["atom-123", "atom-456", ...]
})
```

### 4. Deterministic Sampling

```python
resp = await self.ollama.complete(
    ...,
    temperature=0.0,
    seed=42  # if supported
)
```

---

## Evidence Carry-Through Test (Theoretical)

Given current code, a manual test would likely reveal:

- Some sentences **without** citations
- Citation keys that **don't match** any atom ID (if HybridRetriever generates arbitrary keys)
- Difficulty reconstructing which atoms support which claims

Because `atom_ids_used` is not stored, the test cannot be automated. The only way to verify is:

1. Rerun the entire synthesis pipeline (with same atoms)
2. Compare resulting prose character-by-character

Without deterministic LLM and stored atom list, this is **not feasible**.

---

## Verdict

**Carry-through status:** FAIL (by structure, not by accident)

**Primary reasons:**

1. No structured `atom_ids_used` storage → no machine-checkable lineage
2. No validator that every sentence cites a source
3. Inference not explicitly forbidden → uncited claims possible
4. Word count pressure encourages filler without citations

**To fix:**

- Implement `atom_ids_used` collection during synthesis
- Add post-generation citation validation
- Remove MINIMUM 1000 WORDS from prompt
- Add explicit "no inference" constraint
- Enforce deterministic sampling

---

**Wave 1 Checkpoint:** Ready for user review. Proceed to final verification compilation?
