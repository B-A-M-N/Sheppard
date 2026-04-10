"""
distillation_pipeline.py — Main orchestrator for the multi-pass knowledge compiler.

Pipeline:
  0. Gate: classify_source_quality → skip dictionaries/nav pages
  0b. Gate: embedding-assisted source quality
  1. Extract: MODE: EXTRACT_ATOMS → strict {"atoms": [...]}
  1.5. Structural Validation: cheap local checks
  2. Conditional Atomization: ONLY if >30% fragments
  2.5. Embedding-based atom deduplication
  3. Critique: MODE: CRITIQUE_ATOMS → validate/repair
  3.5. Semantic drift check
  3.7. Semantic recovery — score + repair borderline atoms
  4. Quality Gates: final hard filter
  Fallback 1: Score-based recovery
  Fallback 2: COMPRESSION-FIRST — LLM derives claims from ANY text
"""

import logging
import re
from typing import Any, Dict, List, Optional

from src.utils.knowledge_unit import _make_unit
from src.utils.source_classifier import classify_source_quality
from src.utils.embedding_gates import (
    _embed_source_quality_check,
    _embed_atom_dedup,
    _check_semantic_drift,
)
from src.utils.atom_quality import _classify_atom_quality, _structural_validation


class ExtractionError(Exception):
    """Raised when atom extraction fails due to LLM failure, not empty content."""
    pass

from src.utils.llm_schema_guard import (
    _call_llm_with_schema_guard,
    _normalize_single_atom,
    _normalize_single_atom_fallback,
)
from src.utils.llm_schemas import (
    ATOM_EXTRACTION_SCHEMA,
    CRITIQUE_SCHEMA,
    COMPRESSION_SCHEMA,
    _COMPRESS_PROMPT,
)
from src.utils.entity_filter import _extract_entities_from_atoms
from src.utils.normalize_atom_schema import normalize_atom_schema

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Compression-first distillation
# ──────────────────────────────────────────────────────────────────────

async def llm_compress_to_claims(
    text: str,
    topic: str,
    llm_client,
    max_claims: int = 10
) -> List[Dict[str, Any]]:
    """
    Compression-first extraction: converts ANY text into knowledge claims.
    Uses grammar-constrained decoding (COMPRESSION_SCHEMA) to guarantee valid JSON.
    Always returns at least 1 claim if the text is non-empty.
    """
    if not text or len(text.strip()) < 20:
        return []

    truncated = text[:6000]
    prompt = _COMPRESS_PROMPT.format(text=truncated)

    result = await _call_llm_with_schema_guard(
        llm_client, prompt, expected_schema='claims',
        temperature=0.1, max_tokens=4096,
        error_prefix="Compress",
        format=COMPRESSION_SCHEMA
    )

    if result is None:
        raise ExtractionError("Compression: LLM call failed during claim extraction")

    if not result:
        # Empty is better than garbage — let the upstream fallback handle it
        logger.warning(f"[Distillery] Compress: LLM produced zero claims — returning empty")
        return []

    units = []
    for item in result:
        if not isinstance(item, dict):
            continue
        norm = normalize_atom_schema(item)
        content = norm.get('text', '').strip()
        if not content or len(content) < 10:
            continue
        if not content.endswith(('.', '!', '?')):
            sentences = re.split(r'(?<=[.!?])\s+', content)
            content = sentences[0] if sentences else content
            if not content.endswith(('.', '!', '?')):
                content += '.'
        units.append(_make_unit(
            text=content,
            confidence=float(item.get('confidence', 0.5)),
            atom_type='claim',
            tags=['compressed'],
        ))

    logger.info(f"[Distillery] Compress: {len(units)} units from {len(text)}-char text")
    return units[:max_claims]


# ──────────────────────────────────────────────────────────────────────
# Pipeline passes
# ──────────────────────────────────────────────────────────────────────

async def _extract_raw_atoms(llm_client, text: str, topic: str, source_type: str = 'standard'):
    """Pass 1: Extraction with source-type-aware generation contract."""
    focus_instructions = {
        'academic': "Focus on: mechanisms, architectures, equations, tradeoffs, metrics, experimental results.",
        'standard': "Focus on: findings, methods, architectures, algorithms, metrics, definitions.",
    }
    focus = focus_instructions.get(source_type, focus_instructions['standard'])

    prompt = f"""MODE: EXTRACT_ATOMS

You are a knowledge extraction engine. You are in extraction mode ONLY.
You MUST return JSON with the key "atoms". If you return anything else, it is invalid.

OUTPUT FORMAT — respond with ONLY this JSON structure:
{{"atoms": [{{"type": "claim", "content": "complete factual statement, 20-300 characters."}}]}}

KNOWLEDGE ATOM CONTRACT — every "content" value MUST:
✅ Be a COMPLETE sentence (subject + verb + object)
✅ Be UNDERSTANDABLE without external context
✅ Express a CONCRETE, FALSIFIABLE claim
✅ End with a period
✅ Be at least 8 words
✅ Be 20-300 characters (1-3 sentences)
✅ Use third person (no "our model", "this paper", "we found")

❌ NEVER produce:
- Noun phrases ("Prior methods", "Classification networks")
- Clause fragments ("Using CRNNs with convolutional layers...")
- Section headings or titles
- URLs or citations alone
- Meta-statements about the document ("This document discusses...")
- Critique or evaluation of the atoms
- Reasoning or explanation of your choices

GRANULARITY RULES:
- Extract ONE finding per atom — never combine multiple findings into one atom
- Do NOT split one finding across multiple atoms
- Include specific metrics, numbers, or names when present

EXAMPLE — GOOD atom:
"ResNet-50 achieves 76.0% top-1 accuracy on ImageNet with 3.8 billion FLOPs per inference."

EXAMPLE — BAD atom (combines multiple findings):
"ResNet-50 achieves 76% accuracy. It uses residual connections and was trained on 8 GPUs."

EXAMPLE — BAD atom (too short, no metric):
"ResNet uses residual connections."

{focus}

Additionally, prioritize extracting NAMED ENTITIES — these are critical for discovery:
- Named architectures (e.g., ResNet, Transformer, BERT, CNN, RNN, GPT)
- Algorithms and methods (e.g., Q-learning, PPO, backpropagation, attention)
- Papers, datasets, or benchmarks (e.g., ImageNet, SQuAD, GLUE)
- Specific techniques (e.g., dropout, batch normalization, contrastive learning)
- Frameworks and libraries (e.g., PyTorch, TensorFlow, JAX)

DOCUMENT:
{text[:4000]}
"""
    return await _call_llm_with_schema_guard(
        llm_client, prompt, expected_schema='atoms',
        temperature=0.1, max_tokens=8192,
        error_prefix="Pass 1",
        format=ATOM_EXTRACTION_SCHEMA
    )


async def _atomize_fragments(llm_client, raw_atoms, topic):
    """Pass 2: Atomization — rewrite fragments into complete sentences."""
    valid_atoms = []
    fragments = []

    for atom in raw_atoms:
        norm = normalize_atom_schema(atom)
        content = norm.get('text', '')
        quality = _classify_atom_quality(content)
        if quality == 'VALID' and not content.startswith('http'):
            valid_atoms.append(atom)
        else:
            fragments.append(atom)

    if not fragments:
        return valid_atoms

    fragment_list = "\n".join(
        f"{i+1}. {normalize_atom_schema(a).get('text', '')}" for i, a in enumerate(fragments[:15])
    )

    prompt = f"""MODE: EXTRACT_ATOMS

Rewrite each fragment below into a complete, standalone factual statement about {topic}.

OUTPUT FORMAT — respond with ONLY this JSON structure:
{{"atoms": [{{"content": "complete sentence."}}]}}

RULES:
- Each output MUST be a complete sentence with subject + verb
- Preserve the original meaning — do NOT invent new facts
- Expand pronouns ("our model" → "the proposed model")
- Each must be at least 8 words and end with a period
- If a fragment cannot be completed, omit it from the output

FRAGMENTS:
{fragment_list}
"""
    rewritten = await _call_llm_with_schema_guard(
        llm_client, prompt, expected_schema='atoms',
        temperature=0.2, max_tokens=4096,
        error_prefix="Pass 2",
        format=ATOM_EXTRACTION_SCHEMA
    )
    if rewritten is None:
        raise ExtractionError("Pass 2: LLM call failed during atomization")

    result = list(valid_atoms)
    for rw in rewritten:
        norm = normalize_atom_schema(rw)
        content = norm.get('text', '').strip()
        if len(content) >= 30:
            result.append(_make_unit(text=content, confidence=0.6, atom_type='claim'))

    return result


async def _critique_and_repair(llm_client, atoms):
    """Pass 3: Critique + repair with semantic drift detection."""
    if not atoms:
        return []

    atom_list = "\n".join(
        f"{i+1}. [{a.get('atom_type', a.get('type', 'claim'))}] {normalize_atom_schema(a).get('text', '')}"
        for i, a in enumerate(atoms[:20])
    )

    prompt = f"""MODE: CRITIQUE_ATOMS

You are a quality reviewer ONLY. You MUST return JSON with the key "critique".
You MUST NOT return atoms, extraction results, or any other schema.

OUTPUT FORMAT:
{{"critique": [
  {{"index": 1, "valid": true}},
  {{"index": 2, "valid": false, "reason": "Fragment — no verb", "fix": "Complete sentence version or null"}}
]}}

CRITERIA:
1. COMPLETE SENTENCE: Has subject + verb + object?
2. STANDALONE: Understandable without external context?
3. CONCRETE: Makes a specific, falsifiable claim?
4. NOT A FRAGMENT: Not a clause, label, or heading?

If valid=true, no reason or fix needed.
If valid=false, provide reason AND a fixed version (or null if unfixable).

ATOMS TO REVIEW:
{atom_list}
"""
    critique_result = await _call_llm_with_schema_guard(
        llm_client, prompt, expected_schema='critique',
        temperature=0.0, max_tokens=4096,
        error_prefix="Pass 3",
        format=CRITIQUE_SCHEMA
    )

    if critique_result is None:
        raise ExtractionError("Pass 3: LLM call failed during critique")

    if not critique_result:
        logger.warning("[Distillery] Pass 3: Critique produced no results, keeping original atoms")
        return atoms

    result = []
    applied_fixes = 0
    dropped = 0
    seen_content = set()

    def _content_key(text: str) -> str:
        return text.strip().lower()[:200]

    for item in critique_result:
        if not isinstance(item, dict):
            continue
        index = item.get('index', 0)
        valid = item.get('valid', False)
        fix = item.get('fix')

        if valid and 0 < index <= len(atoms):
            orig_atom = atoms[index - 1]
            content = normalize_atom_schema(orig_atom).get('text', '')
            key = _content_key(content)
            if key not in seen_content:
                seen_content.add(key)
                result.append(orig_atom)
        elif fix and isinstance(fix, str) and len(fix) >= 30:
            orig = atoms[index - 1] if 0 < index <= len(atoms) else {}
            fixed_content = fix.strip()
            key = _content_key(fixed_content)
            if key not in seen_content:
                seen_content.add(key)
                result.append(_make_unit(
                    text=fixed_content,
                    confidence=float(orig.get('confidence', 0.5)),
                    atom_type=str(orig.get('type', 'claim')),
                ))
                applied_fixes += 1
        elif valid is False and 0 < index <= len(atoms):
            dropped += 1

    if applied_fixes:
        logger.info(f"[Distillery] Pass 3: Applied {applied_fixes} repairs, dropped {dropped} atoms")

    if not result:
        logger.warning("[Distillery] Pass 3: No valid atoms after critique, keeping originals")
        return atoms

    return result


# ──────────────────────────────────────────────────────────────────────
# Main orchestrator
# ──────────────────────────────────────────────────────────────────────

async def extract_technical_atoms(
    llm_client,
    text: str,
    topic: str,
    source_url: str = ''
) -> List[Dict[str, Any]]:
    """
    Multi-pass knowledge compiler with compression-first fallback.

    Gate 0a: String-based source quality classification (fast skip)
    Gate 0b: Embedding-based source quality scoring (information density check)
    Pass 1: Extraction (temp=0.1) — looks for pre-existing atomic facts
    Pass 1.5: Structural validation (cheap, local)
    Pass 2: Conditional atomization (ONLY if >30% fragments)
    Pass 2.5: Embedding-based atom deduplication (semantic merge)
    Pass 3: Critique + Repair with semantic drift detection (temp=0.0)
    Pass 3.5: Semantic drift check
    Pass 3.7: SEMANTIC RECOVERY — score + repair borderline atoms
    Pass 4: Quality gates (safety net on scored atoms)
    Fallback 1: Score-based recovery of borderline atoms
    Fallback 2: COMPRESSION-FIRST — LLM derives claims from ANY text (guaranteed yield)
    """
    # --- GATE 0a: String-based classification (fast) ---
    source_type = classify_source_quality(source_url, text)
    if source_type == 'skip':
        logger.info(f"[Distillery] Gate 0a: Skipping low-value source for '{source_url[:60]}'")
        return []

    # --- GATE 0b: Embedding-based information density check ---
    try:
        score_low, score_high, should_skip = await _embed_source_quality_check(text, llm_client)
        if should_skip:
            logger.info(f"[Distillery] Gate 0b: Embedding skip — low={score_low:.2f}, high={score_high:.2f} for '{source_url[:60]}'")
            return []
        if score_low > 0 or score_high > 0:
            logger.info(f"[Distillery] Gate 0b: Embedding scores — low={score_low:.2f}, high={score_high:.2f}")
    except Exception as e:
        logger.warning(
            f"[Distillery] Gate 0b embedding check failed for source "
            f"(topic={topic}, url={source_url[:60]}): {e}. "
            f"Falling back to string quality check."
        )

    try:
        # --- CHUNKING: Token-based chunked extraction (replaces 4000-char truncation) ---
        from src.utils.extract_chunker import chunk_for_extraction, _count_tokens

        token_count = _count_tokens(text)

        if token_count > 3500:
            # Chunked extraction path
            chunks = chunk_for_extraction(text)
            logger.info(
                f"[Distillery] Source is {token_count} tokens — "
                f"chunking into {len(chunks)} extraction chunks"
            )

            all_raw_atoms = []
            for i, chunk in enumerate(chunks):
                chunk_atoms = await _extract_raw_atoms(llm_client, chunk, topic, source_type)
                if chunk_atoms:
                    all_raw_atoms.extend(chunk_atoms)
                logger.info(f"[Distillery] Chunk {i+1}/{len(chunks)}: {len(chunk_atoms or [])} atoms")

            if not all_raw_atoms:
                logger.info(f"[Distillery] Zero atoms from all {len(chunks)} chunks")
                return []

            # Cross-chunk dedup with lower threshold
            raw_atoms = await _embed_atom_dedup(all_raw_atoms, llm_client, threshold=0.88)
            dedup_count = len(all_raw_atoms) - len(raw_atoms)
            if dedup_count > 0:
                logger.info(f"[Distillery] Cross-chunk dedup: removed {dedup_count} duplicates")
        else:
            # Single-pass extraction (existing behavior)
            raw_atoms = await _extract_raw_atoms(llm_client, text, topic, source_type)

        if not raw_atoms:
            logger.info(f"[Distillery] Pass 1: Zero atoms extracted for '{topic}'")
            return []
        logger.info(f"[Distillery] Pass 1: Extracted {len(raw_atoms)} atoms")

        # --- PASS 1.5: Structural Validation ---
        quality_report = _structural_validation(raw_atoms)
        logger.info(f"[Distillery] Pass 1.5: {quality_report['VALID']} valid, {quality_report['FRAGMENT']} fragment, {quality_report['WEAK']} weak")

        # Guard: log if filter is destroying all atoms
        if quality_report['VALID'] == 0 and len(raw_atoms) > 0:
            logger.warning(
                f"[Distillery] FILTER WARNING: Zero valid atoms from {len(raw_atoms)} extracted. "
                f"Sample: {normalize_atom_schema(raw_atoms[0]).get('text', '')[:100]!r}"
            )

        # --- PASS 2: Conditional Atomization ---
        fragment_pct = (quality_report['FRAGMENT'] + quality_report['WEAK']) / max(len(raw_atoms), 1)
        if fragment_pct > 0.30:
            logger.info(f"[Distillery] Pass 2: {fragment_pct:.0%} fragments — activating atomization")
            atomized = await _atomize_fragments(llm_client, raw_atoms, topic)
            logger.info(f"[Distillery] Pass 2: Atomized to {len(atomized)} atoms")
        else:
            logger.info(f"[Distillery] Pass 2: {fragment_pct:.0%} fragments — skipping atomization")
            atomized = raw_atoms

        # --- PASS 2.5: Embedding-based deduplication ---
        deduped = await _embed_atom_dedup(atomized, llm_client, threshold=0.92)
        dedup_count = len(atomized) - len(deduped)
        if dedup_count > 0:
            logger.info(f"[Distillery] Pass 2.5: Merged {dedup_count} semantically duplicate atoms ({len(deduped)} remaining)")
        else:
            logger.info(f"[Distillery] Pass 2.5: No semantic duplicates found")

        # --- PASS 3: Critique + Repair with drift detection ---
        critiqued = await _critique_and_repair(llm_client, deduped)
        logger.info(f"[Distillery] Pass 3: After critique+repair, {len(critiqued)} atoms")

        # --- PASS 3.5: Semantic drift check ---
        drift_flagged = []
        for atom in critiqued:
            sim, drifting = await _check_semantic_drift(atom, text, llm_client, threshold=0.55)
            if drifting:
                atom['_drift_score'] = sim
                drift_flagged.append(atom)
        if drift_flagged:
            logger.info(f"[Distillery] Pass 3.5: {len(drift_flagged)} atoms flagged for semantic drift (will be filtered)")
            drift_ids = {id(a) for a in drift_flagged}
            critiqued = [a for a in critiqued if id(a) not in drift_ids]

        # --- PASS 3.7: SEMANTIC RECOVERY ---
        from src.utils.semantic_repair import repair_atom_batch
        from src.utils.atom_scorer import filter_atoms_by_score, ACCEPTANCE_THRESHOLD

        accepted, repair_candidates, low_quality = filter_atoms_by_score(
            critiqued, min_score=ACCEPTANCE_THRESHOLD, max_repair_candidates=15
        )
        logger.info(
            f"[Distillery] Pass 3.7: Scoring — {len(accepted)} accepted, "
            f"{len(repair_candidates)} repair candidates, {len(low_quality)} rejected"
        )

        if repair_candidates:
            repaired = await repair_atom_batch(
                repair_candidates, topic, llm_client,
                use_llm=True, max_llm_repairs=10
            )
            repaired_accepted, _, _ = filter_atoms_by_score(
                repaired, min_score=ACCEPTANCE_THRESHOLD
            )
            logger.info(f"[Distillery] Pass 3.7: Repaired {len(repaired_accepted)} atoms from {len(repair_candidates)} candidates")
            accepted.extend(repaired_accepted)
        else:
            logger.info(f"[Distillery] Pass 3.7: No repair candidates needed")

        # --- PASS 4: Quality Gates ---
        final_atoms = []
        for atom in accepted:
            normalized = _normalize_single_atom(atom)
            if normalized:
                if "scoring" in atom:
                    normalized["scoring"] = atom["scoring"]
                final_atoms.append(normalized)

        # ─── FALLBACK 1: Low-quality scoring recovery ───
        if not final_atoms and low_quality:
            logger.info(f"[Distillery] Pass 4: Zero yield — attempting low-quality recovery")
            low_quality.sort(key=lambda a: a.get("scoring", {}).get("score", 0), reverse=True)
            for atom in low_quality[:5]:
                normalized = _normalize_single_atom_fallback(atom)
                if normalized:
                    if "scoring" in atom:
                        normalized["scoring"] = atom["scoring"]
                    final_atoms.append(normalized)
            logger.info(f"[Distillery] Fallback 1: recovered {len(final_atoms)} atoms")

        # ─── FALLBACK 2: COMPRESSION-FIRST (guaranteed yield) ───
        if not final_atoms and len(text.strip()) >= 50:
            logger.info(f"[Distillery] Pass 4: Zero yield from extraction — activating compression-first distillation")
            try:
                compressed = await llm_compress_to_claims(text, topic, llm_client)
                if compressed:
                    for atom in compressed:
                        normalized = _normalize_single_atom(atom)
                        if normalized:
                            normalized["compressed"] = True
                            final_atoms.append(normalized)
                    logger.info(f"[Distillery] Compression-first: {len(final_atoms)} claims derived from raw text")
            except ExtractionError:
                logger.warning(f"[Distillery] Compression-first LLM call failed — skipping fallback")
            except Exception as e:
                logger.warning(f"[Distillery] Compression-first failed: {e}")
                sentences = re.split(r'(?<=[.!?])\s+', text[:500])
                best = max(sentences, key=len) if sentences else text[:200]
                if best.strip() and len(best.strip()) >= 15:
                    best = best.strip()
                    if not best.endswith(('.', '!', '?')):
                        best = best.rsplit('.', 1)[0] + '.' if '.' in best else best + '.'
                    final_atoms.append(_make_unit(
                        text=best, confidence=0.2,
                        atom_type='claim', tags=['compressed', 'fallback', 'emergency'],
                    ))
                    logger.info(f"[Distillery] Emergency: created single KnowledgeUnit from text")

        if final_atoms:
            logger.info(f"[Distillery] Final: {len(final_atoms)} atoms stored for '{topic}'")
        else:
            logger.warning(f"[Distillery] All passes produced zero valid atoms for '{topic}'")

        # --- ENTITY EXTRACTION: Extract named entities for Frontier discovery ---
        entities = _extract_entities_from_atoms(final_atoms)
        if entities:
            logger.info(f"[Distillery] Extracted {len(entities)} discovery entities: {entities[:10]}")

        return final_atoms

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"[Distillery] extract_technical_atoms FAILED: {e}\n{tb}")
        raise ExtractionError(f"Extraction pipeline failed: {e}") from e
