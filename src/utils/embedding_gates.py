"""
embedding_gates.py — Embedding-assisted quality checks, dedup, drift detection,
and semantic entity extraction.

All embeddings route through embedding_distiller.safe_embed() to guarantee
no context overflow.
"""

import logging
import math
from typing import Any, List, Optional, Tuple

from src.utils.embedding_distiller import safe_embed, gate_source, MAX_TOKENS
from src.utils.llm_schemas import _LOW_VALUE_CENTROID_TEXTS, _HIGH_VALUE_CENTROID_TEXTS
from src.utils.entity_filter import (
    _is_artifact_fragment, _is_generic_singleton, _is_language_list,
    _is_camel_case, _classify_tier,
)

logger = logging.getLogger(__name__)


def _cosine_similarity(a, b):
    """Cosine similarity between two vectors. Pure math, no dependencies."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ──────────────────────────────────────────────────────────────────────
# Gate 0b: Embedding-assisted source quality
# ──────────────────────────────────────────────────────────────────────

async def _embed_source_quality_check(text, llm_client):
    """
    Uses embedding_distiller.safe_embed() to guarantee no context overflow.
    Compares source text against reference centroids for information density.

    Returns: (score_low, score_high, should_skip)
    """
    try:
        gate_result, token_count = gate_source(text)
        if gate_result == "DROP":
            logger.info(f"[Distillery] Gate 0: Dropping high-noise source ({token_count} tokens)")
            return 0.0, 0.0, True

        if token_count > MAX_TOKENS * 3:
            from src.utils.embedding_distiller import distill_for_embedding
            chunks, _ = distill_for_embedding(text)
            if not chunks:
                logger.info(f"[Distillery] Gate 0: Pre-distillation produced no chunks ({token_count} tokens)")
                return 0.0, 0.0, True
            embed_text = chunks[0] if len(chunks) == 1 else " ".join(chunks[:3])
        else:
            embed_text = text

        async def embed_fn(chunk):
            return await llm_client.generate_embedding(chunk)

        source_emb, embed_stats = await safe_embed(embed_text, embed_fn)
        if not source_emb:
            logger.warning(f"[Distillery] Gate 0: Embedding failed after distillation — marking as skip")
            return 0.0, 0.0, True

        logger.debug(
            f"[Distillery] Gate 0: Embedded {embed_stats['distillation'].get('chunks', 1)} chunks "
            f"({embed_stats['distillation'].get('sentences_filtered', 0)} atoms)"
        )

        low_scores = []
        high_scores = []
        for ref_text in _LOW_VALUE_CENTROID_TEXTS:
            ref_emb, _ = await safe_embed(ref_text, embed_fn)
            if ref_emb:
                low_scores.append(_cosine_similarity(source_emb, ref_emb))
        for ref_text in _HIGH_VALUE_CENTROID_TEXTS:
            ref_emb, _ = await safe_embed(ref_text, embed_fn)
            if ref_emb:
                high_scores.append(_cosine_similarity(source_emb, ref_emb))

        score_low = max(low_scores) if low_scores else 0.0
        score_high = max(high_scores) if high_scores else 0.0
        should_skip = score_low > 0.85 and score_high < 0.60

        return score_low, score_high, should_skip

    except Exception as e:
        logger.warning(f"[Distillery] Embedding source quality check failed: {e}")
        return 0.0, 0.0, False


# ──────────────────────────────────────────────────────────────────────
# Pass 2.5: Embedding-based atom deduplication
# ──────────────────────────────────────────────────────────────────────

async def _embed_atom_dedup(atoms, llm_client, threshold=0.92):
    """Groups semantically identical atoms. Merges duplicates, keeps highest-confidence."""
    if len(atoms) < 2:
        return atoms

    async def embed_fn(chunk):
        return await llm_client.generate_embedding(chunk)

    embeddings = []
    for i, atom in enumerate(atoms):
        content = atom.get('text', atom.get('content', ''))
        emb, _ = await safe_embed(content, embed_fn)
        if emb:
            embeddings.append(emb)
        else:
            logger.debug(f"[Distillery] Pass 2.5: Atom {i} embed failed, using zero vector")
            embeddings.append([0.0] * 1024)

    n = len(atoms)
    kept = [True] * n
    for i in range(n):
        if not kept[i]:
            continue
        for j in range(i + 1, n):
            if not kept[j]:
                continue
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            if sim >= threshold:
                if atoms[j].get('confidence', 0) > atoms[i].get('confidence', 0):
                    kept[i] = False
                else:
                    kept[j] = False

    return [atoms[i] for i in range(n) if kept[i]]


# ──────────────────────────────────────────────────────────────────────
# Pass 3.5: Semantic drift detection
# ──────────────────────────────────────────────────────────────────────

async def _check_semantic_drift(atom, source_text, llm_client, threshold=0.55):
    """
    If an atom's content has low cosine similarity with its source,
    it likely hallucinated or drifted.

    Returns: (similarity_score, is_drifting)
    Embedding failure is INCONCLUSIVE, not a drift verdict.
    """
    content = atom.get('text', atom.get('content', ''))
    if not content or not source_text:
        return 0.5, False

    try:
        # Truncate source to avoid context overflow — first 2000 chars is representative
        truncated_source = source_text[:2000]

        async def embed_fn(chunk):
            return await llm_client.generate_embedding(chunk)

        atom_emb, _ = await safe_embed(content, embed_fn)
        source_emb, _ = await safe_embed(truncated_source, embed_fn)
        if not atom_emb or not source_emb:
            return 0.5, False

        sim = _cosine_similarity(atom_emb, source_emb)
        return sim, sim < threshold

    except Exception as e:
        logger.debug(f"[Distillery] Pass 3: Semantic drift check failed: {e}")
        return 0.0, True


# ──────────────────────────────────────────────────────────────────────
# Semantic entity extraction with embedding-assisted clustering
# ──────────────────────────────────────────────────────────────────────

async def _embed_entities(entities, ollama_client):
    """Generate embeddings for entity strings. Falls back to zero-vector on failure."""
    async def embed_fn(chunk):
        return await ollama_client.generate_embedding(chunk)

    embeddings = []
    for entity in entities:
        emb, _ = await safe_embed(entity, embed_fn)
        embeddings.append(emb if emb else [0.0] * 1024)
    return embeddings


def _cluster_by_similarity(entities, embeddings, threshold=0.75):
    """Greedy clustering by cosine similarity. Returns list of clusters (index lists)."""
    n = len(entities)
    if n == 0:
        return []
    assigned = [False] * n
    clusters = []
    for i in range(n):
        if assigned[i]:
            continue
        cluster = [i]
        assigned[i] = True
        for j in range(i + 1, n):
            if assigned[j]:
                continue
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            if sim >= threshold:
                cluster.append(j)
                assigned[j] = True
        clusters.append(cluster)
    return clusters


def _pick_cluster_representative(cluster_indices, entities):
    """Pick best form from cluster: prefer longest with proper capitalization."""
    forms = [entities[i] for i in cluster_indices]
    def form_score(f):
        score = len(f)
        words = f.split()
        if all(w[0].isupper() for w in words if w):
            score += 10
        if f[0].isupper() and not f.isupper():
            score += 5
        return score
    return max(forms, key=form_score)


async def _extract_entities_semantic(atoms, ollama_client):
    """
    Full semantic entity extraction with embedding-assisted clustering.
    Pipeline: extract → structural reject → embed → cluster → cross-frequency → tier.
    Returns list of unique, semantically deduplicated entity names.
    """
    SKIP_PREFIXES = {
        "the", "a", "an", "this", "that", "these", "those",
        "its", "our", "their", "his", "her", "my", "your",
    }

    raw_entities = []
    for atom in atoms:
        content = atom.get("content", "")
        if not content:
            continue
        words = content.replace("-", " ").replace("_", " ")
        for ch in ".,;:!?()[]{}\"'\\/":
            words = words.replace(ch, " ")
        tokens = words.split()
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if _is_camel_case(token):
                raw_entities.append(token)
            if token and len(token) > 1 and token[0].isupper():
                if token.lower() in SKIP_PREFIXES:
                    i += 1
                    continue
                phrase = [token]
                j = i + 1
                while j < len(tokens) and len(tokens[j]) > 1 and tokens[j][0].isupper():
                    if tokens[j].lower() not in SKIP_PREFIXES:
                        phrase.append(tokens[j])
                    j += 1
                if len(phrase) >= 2:
                    raw_entities.append(" ".join(phrase))
                    i = j
                    continue
            i += 1

    candidates = [e for e in raw_entities if not _is_artifact_fragment(e)
                  and not _is_generic_singleton(e)
                  and not _is_language_list(e)
                  and len(e) > 2]
    if not candidates:
        return []

    embeddings = await _embed_entities(candidates, ollama_client)
    clusters = _cluster_by_similarity(candidates, embeddings, threshold=0.75)

    result = []
    for cluster in clusters:
        representative = _pick_cluster_representative(cluster, candidates)
        cross_freq = len(cluster)
        tier = _classify_tier(representative, cross_freq=cross_freq)
        if tier == "expandable":
            result.append(representative)

    return result
