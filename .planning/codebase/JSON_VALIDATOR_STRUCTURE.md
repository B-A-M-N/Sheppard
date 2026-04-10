# Structural Analysis: `src/utils/json_validator.py` (2183 lines)

**Analysis Date:** 2026-04-10

---

## 1. Top-Level Symbols (name, line start, line count)

### Module-Level Constants & Schemas
| Symbol | Line | Lines | Description |
|--------|------|-------|-------------|
| `ATOM_EXTRACTION_SCHEMA` | 82 | 20 | JSON schema for atom extraction |
| `CRITIQUE_SCHEMA` | 103 | 17 | JSON schema for critique/repair |
| `COMPRESSION_SCHEMA` | 121 | 18 | JSON schema for compression fallback |
| `_LOW_VALUE_SOURCE_PATTERNS` | 279 | 9 | List of URL/content patterns to skip |
| `_LOW_VALUE_CENTROID_TEXTS` | 335 | 9 | Low-quality text centroids for embedding comparison |
| `_HIGH_VALUE_CENTROID_TEXTS` | 345 | 9 | High-quality text centroids for embedding comparison |
| `_COMPRESS_PROMPT` | 715 | 24 | LLM prompt template for compression |
| `_ARTIFACT_PATTERNS` | 1007 | 14 | Set of document/web artifact patterns |

### Module-Level Functions
| Symbol | Line | Lines | Description |
|--------|------|-------|-------------|
| `_make_unit` | 38 | 39 | KnowledgeUnit factory — canonical output type |
| `classify_source_quality` | 290 | 27 | Gate 0a: string-based source classification |
| `_cosine_similarity` | 319 | 11 | Vector math utility |
| `_embed_source_quality_check` | 356 | 67 | Gate 0b: embedding-assisted source quality |
| `_embed_atom_dedup` | 425 | 43 | Pass 2.5: embedding-based atom deduplication |
| `_check_semantic_drift` | 470 | 39 | Pass 3.5: drift detection between atom and source |
| `_has_verb` | 510 | 17 | Cheap verb detection heuristic |
| `_classify_atom_quality` | 529 | 18 | Structural atom quality classifier |
| `llm_compress_to_claims` | 741 | 58 | Compression-first extraction |
| `extract_technical_atoms` | 800 | 157 | **Main pipeline** — multi-pass knowledge compiler |
| `_is_artifact_fragment` | 1024 | 32 | Structural artifact rejection |
| `_is_generic_singleton` | 1058 | 45 | Generic word rejection |
| `_is_language_list` | 1105 | 30 | Language-list artifact detection |
| `_conceptual_suffix_score` | 1137 | 16 | Morphological bonus scoring |
| `_structural_stability` | 1155 | 52 | Structural entity scoring |
| `_classify_tier` | 1209 | 33 | Entity tier classification |
| `_canonicalize` | 1244 | 23 | Entity canonicalization/dedup |
| `_is_camel_case` | 1269 | 9 | CamelCase detection |
| `_compute_cross_frequency` | 1280 | 10 | Cross-frequency computation |
| `_filter_and_dedup` | 1292 | 34 | Full cognitive gate for entities |
| `_extract_entities_from_atoms` | 1328 | 61 | Named entity extraction from atoms |
| `_embed_entities` | 1403 | 17 | Embed entities via safe_embed |
| `_cluster_by_similarity` | 1422 | 29 | Greedy clustering by cosine similarity |
| `_pick_cluster_representative` | 1453 | 19 | Pick best form from cluster |
| `_extract_entities_semantic` | 1474 | 82 | Full semantic entity extraction pipeline |
| `_structural_validation` | 1558 | 9 | Cheap local validation |
| `_extract_raw_atoms` | 1569 | 82 | Pass 1: extraction with LLM |
| `_call_llm_with_schema_guard` | 1653 | 76 | Generic LLM call with schema guard |
| `_atomize_fragments` | 1731 | 52 | Pass 2: rewrite fragments |
| `_critique_and_repair` | 1785 | 82 | Pass 3: critique + repair |
| `_extract_atoms_from_llm_response` | 1887 | 61 | Parse LLM response into atoms |
| `_normalize_atom_list` | 1950 | 53 | Normalize JSON structures to atom list |
| `_normalize_critique_item` | 2005 | 34 | Normalize critique items |
| `_normalize_single_atom` | 2041 | 46 | Single atom → KnowledgeUnit dict |
| `_normalize_single_atom_fallback` | 2089 | 40 | Relaxed normalization for fallback |
| `_parse_lines_fallback` | 2131 | 51 | Last-resort line parser |

### Classes
| Symbol | Line | Lines | Description |
|--------|------|-------|-------------|
| `JSONValidator` | 143 | 237 | JSON validation/repair class |
| `WrongSchemaError` | 1884 | 3 | Custom exception |

---

## 2. Logical Groups

### Group A: JSON Validation & Repair (lines 143–379)
- `JSONValidator` class (validate_and_fix_json, _create_format_repair_prompt, _create_correction_prompt, _extract_json, _validate_schema, _create_fallback_response)
- `ATOM_EXTRACTION_SCHEMA`, `CRITIQUE_SCHEMA`, `COMPRESSION_SCHEMA`
- `_make_unit`
- **Responsibility:** Parse, validate, and repair JSON from LLM responses

### Group B: LLM Call Infrastructure (lines 1653–1728)
- `_call_llm_with_schema_guard`
- `_extract_atoms_from_llm_response`
- `_normalize_atom_list`
- `_normalize_single_atom`
- `_normalize_single_atom_fallback`
- `_normalize_critique_item`
- `_parse_lines_fallback`
- `WrongSchemaError`
- **Responsibility:** Generic LLM communication, response parsing, normalization

### Group C: Main Distillation Pipeline (lines 800–956)
- `extract_technical_atoms`
- `llm_compress_to_claims`
- **Responsibility:** Orchestrates the full multi-pass pipeline

### Group D: Pipeline Passes (lines 1558–1866)
- `_extract_raw_atoms` (Pass 1)
- `_structural_validation` (Pass 1.5)
- `_atomize_fragments` (Pass 2)
- `_critique_and_repair` (Pass 3)
- `_compress_to_claims` (Fallback 2 — also in Group C)
- **Responsibility:** Individual pipeline stages

### Group E: Embedding-Assisted Quality Gates (lines 319–508)
- `_cosine_similarity`
- `_embed_source_quality_check` (Gate 0b)
- `_embed_atom_dedup` (Pass 2.5)
- `_check_semantic_drift` (Pass 3.5)
- `_embed_entities`, `_cluster_by_similarity`, `_pick_cluster_representative`, `_extract_entities_semantic`
- **Responsibility:** Embedding-based quality checks, dedup, drift, clustering

### Group F: Structural Atom Quality (lines 510–546)
- `_has_verb`
- `_classify_atom_quality`
- **Responsibility:** Cheap local atom quality classification (no LLM, no embeddings)

### Group G: Entity Extraction & Cognitive Filter (lines 1007–1555)
- `_ARTIFACT_PATTERNS`
- `_is_artifact_fragment`, `_is_generic_singleton`, `_is_language_list`
- `_conceptual_suffix_score`, `_structural_stability`
- `_classify_tier`, `_canonicalize`, `_is_camel_case`
- `_compute_cross_frequency`, `_filter_and_dedup`
- `_extract_entities_from_atoms`
- **Responsibility:** String-based entity extraction, classification, deduplication

### Group H: Source Classification (lines 279–316)
- `_LOW_VALUE_SOURCE_PATTERNS`
- `classify_source_quality`
- **Responsibility:** Fast source quality gating

---

## 3. Internal Dependency Graph

```
extract_technical_atoms (C)
  ├── classify_source_quality (H)
  ├── _embed_source_quality_check (E)
  ├── _extract_raw_atoms (D) ────────→ _call_llm_with_schema_guard (B)
  ├── _structural_validation (D/F) ──→ _classify_atom_quality (F)
  ├── _atomize_fragments (D) ─────────→ _call_llm_with_schema_guard (B)
  │                                    → _classify_atom_quality (F)
  │                                    → _make_unit (A)
  ├── _embed_atom_dedup (E) ─────────→ _cosine_similarity (E)
  ├── _critique_and_repair (D) ──────→ _call_llm_with_schema_guard (B)
  │                                    → _make_unit (A)
  ├── _check_semantic_drift (E) ─────→ _cosine_similarity (E)
  ├── llm_compress_to_claims (C) ────→ _call_llm_with_schema_guard (B)
  │                                    → _make_unit (A)
  ├── repair_atom_batch (external)
  ├── filter_atoms_by_score (external)
  ├── _normalize_single_atom (B) ────→ _make_unit (A)
  ├── _normalize_single_atom_fallback (B) → _make_unit (A)
  ├── _extract_entities_from_atoms (G) → _filter_and_dedup (G)
  └── _extract_entities_semantic (E) ─→ _embed_entities (E)
                                       → _cluster_by_similarity (E)
                                       → _classify_tier (G)

_extract_atoms_from_llm_response (B)
  ├── _normalize_atom_list (B)
  │     ├── _normalize_single_atom (B)
  │     └── _normalize_critique_item (B)
  └── _parse_lines_fallback (B)

Entity extraction (G)
  ├── _is_artifact_fragment → uses _ARTIFACT_PATTERNS
  ├── _is_generic_singleton
  ├── _is_language_list
  ├── _structural_stability → _conceptual_suffix_score, _is_camel_case
  ├── _classify_tier → calls above 4
  ├── _canonicalize
  ├── _compute_cross_frequency → _canonicalize
  ├── _filter_and_dedup → all above
  └── _extract_entities_from_atoms → _filter_and_dedup

JSONValidator (A) — mostly STANDALONE
  └── _extract_json, _validate_schema, etc. (self-contained)
```

**Key observation:** Group B (LLM call infra) is called by Groups C and D. Group A (`_make_unit`) is called by Groups B, C, D. Group E (embeddings) is called by Group C. Group G (entities) is called by Group C.

---

## 4. External Dependencies

### Imports FROM this module (public API surface)

| Consumer | Imports |
|----------|---------|
| `src/research/condensation/pipeline.py` | `JSONValidator`, `extract_technical_atoms`, `_extract_entities_semantic` |
| `src/research/acquisition/frontier.py` | `JSONValidator` |
| `src/research/system.py:691` | `extract_key_information` ⚠️ **BROKEN** — this function does not exist in the file |

### Imports INTO this module

| Source | Imported |
|--------|----------|
| `src/utils/text_processing` | `repair_json` |
| `src/utils/embedding_distiller` | `safe_embed`, `gate_source`, `distill_for_embedding`, `rough_token_count`, `clean_boilerplate`, `MAX_TOKENS` |
| `src/research/domain_schema` | `KnowledgeUnit` |
| `src/utils/semantic_repair` (lazy import, line 903) | `repair_atom_batch` |
| `src/utils/atom_scorer` (lazy import, line 904) | `filter_atoms_by_score`, `ACCEPTANCE_THRESHOLD` |

### Standard library: `json`, `logging`, `math`, `re`, `typing`, `asyncio`, `hashlib` (inline)

---

## 5. Suggested Module Boundaries

### Proposed file structure:

```
src/utils/
├── json_validator.py          (thin re-export + JSONValidator class only, ~60 lines)
├── knowledge_unit.py          (_make_unit + KnowledgeUnit integration, ~50 lines)
├── atom_quality.py            (structural atom quality, ~50 lines)
├── llm_schema_guard.py        (LLM call infra + normalization, ~250 lines)
├── distillation_pipeline.py   (main pipeline + all passes, ~400 lines)
├── embedding_gates.py         (embedding-based quality/dedup/drift, ~200 lines)
├── entity_filter.py           (cognitive filter + entity extraction, ~250 lines)
├── source_classifier.py       (source quality classification, ~50 lines)
└── llm_schemas.py             (JSON schema constants, ~50 lines)
```

### Detailed split plan:

**`llm_schemas.py`** (new, ~50 lines)
- `ATOM_EXTRACTION_SCHEMA`, `CRITIQUE_SCHEMA`, `COMPRESSION_SCHEMA`
- `_COMPRESS_PROMPT`
- `_LOW_VALUE_SOURCE_PATTERNS`
- `_LOW_VALUE_CENTROID_TEXTS`, `_HIGH_VALUE_CENTROID_TEXTS`
- No internal dependencies

**`knowledge_unit.py`** (new, ~50 lines)
- `_make_unit`
- Depends on: `src/research/domain_schema.KnowledgeUnit`

**`atom_quality.py`** (new, ~50 lines)
- `_has_verb`, `_classify_atom_quality`, `_structural_validation`
- No internal dependencies (pure functions)

**`entity_filter.py`** (new, ~250 lines)
- `_ARTIFACT_PATTERNS`
- `_is_artifact_fragment`, `_is_generic_singleton`, `_is_language_list`
- `_conceptual_suffix_score`, `_structural_stability`, `_is_camel_case`
- `_classify_tier`, `_canonicalize`
- `_compute_cross_frequency`, `_filter_and_dedup`
- `_extract_entities_from_atoms`
- No internal dependencies except `_is_camel_case` → `_structural_stability` chain

**`embedding_gates.py`** (new, ~200 lines)
- `_cosine_similarity`
- `_embed_source_quality_check`, `_embed_atom_dedup`, `_check_semantic_drift`
- `_embed_entities`, `_cluster_by_similarity`, `_pick_cluster_representative`
- `_extract_entities_semantic`
- Depends on: `embedding_distiller` (safe_embed, gate_source, MAX_TOKENS)

**`llm_schema_guard.py`** (new, ~250 lines)
- `WrongSchemaError`
- `_call_llm_with_schema_guard`
- `_extract_atoms_from_llm_response`, `_normalize_atom_list`
- `_normalize_single_atom`, `_normalize_single_atom_fallback`, `_normalize_critique_item`
- `_parse_lines_fallback`
- Depends on: `text_processing.repair_json`, `knowledge_unit._make_unit`, `llm_schemas.*`

**`distillation_pipeline.py`** (new, ~400 lines)
- `extract_technical_atoms` (main orchestrator)
- `_extract_raw_atoms`, `_atomize_fragments`, `_critique_and_repair`
- `llm_compress_to_claims`
- Depends on: ALL other modules above, plus `semantic_repair`, `atom_scorer`

**`source_classifier.py`** (new, ~50 lines)
- `classify_source_quality`
- Depends on: `llm_schemas._LOW_VALUE_SOURCE_PATTERNS`

**`json_validator.py`** (remaining, ~60 lines)
- `JSONValidator` class only
- Re-exports for backward compatibility:
  - `from .distillation_pipeline import extract_technical_atoms`
  - `from .embedding_gates import _extract_entities_semantic`
- Depends on: nothing except stdlib

### Public API migration:

```python
# json_validator.py — backward-compatible re-exports
from .distillation_pipeline import extract_technical_atoms
from .embedding_gates import _extract_entities_semantic

# Fix broken import in system.py:
# from .distillation_pipeline import extract_key_information  # (need to create or redirect)
```

### Notes:
- The `extract_key_information` referenced in `system.py:691` **does not exist** — this is either a dead code path or the function was renamed/removed. Needs investigation.
- `JSONValidator` is imported in `frontier.py` but only used once (line 340-341) for its `_extract_json` method. Consider extracting `_extract_json` as a standalone function if the class is otherwise unused.
- Lazy imports at lines 903-904 (`semantic_repair`, `atom_scorer`) suggest these modules were extracted previously — follow the same pattern for this split.
