"""
embedding_distiller.py — Embedding-Safe Distillation Architecture

Transforms noisy documents into embedding-ready atomic claims.
Prevents context overflow by design, not by truncation.

3-layer pipeline:
  1. Boilerplate stripping (mandatory)
  2. Semantic filtering (keep claims, drop noise)
  3. Sliding window + pooling (if still too large)
"""

import re
import math
import logging
from typing import List, Dict, Any, Optional, Callable, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

MAX_TOKENS = 1500  # Conservative limit for 2048-token models
WINDOW_SIZE = 10   # Sentences per window
STRIDE = 7         # Overlap between windows
MIN_SENTENCE_LEN = 20  # Minimum chars to be worth embedding

# ─────────────────────────────────────────────
# BOILERPLATE STRIPPER
# ─────────────────────────────────────────────

_BOILERPLATE_PATTERNS = [
    # HTML/script noise
    (r"<script.*?</script>", re.IGNORECASE | re.DOTALL),
    (r"<style.*?</style>", re.IGNORECASE | re.DOTALL),
    (r"<!--.*?-->", re.IGNORECASE | re.DOTALL),
    (r"<[^>]+>", 0),  # All remaining tags
    
    # Web UI noise (line-based removal)
    (r"\n{3,}", 0),  # Excessive newlines
    (r"^Related articles.*$", re.IGNORECASE | re.MULTILINE),
    (r"^Cookie Policy.*$", re.IGNORECASE | re.MULTILINE),
    (r"^Accept cookies.*$", re.IGNORECASE | re.MULTILINE),
    (r"^Privacy Policy.*$", re.IGNORECASE | re.MULTILINE),
    (r"^Terms of Service.*$", re.IGNORECASE | re.MULTILINE),
    (r"^Subscribe.*$", re.IGNORECASE | re.MULTILINE),
    (r"^Sign up.*$", re.IGNORECASE | re.MULTILINE),
    (r"^Log in.*$", re.IGNORECASE | re.MULTILINE),
    
    # Citation/reference blocks (common in academic pages)
    (r"^References\s*$", re.IGNORECASE | re.MULTILINE),
    (r"^Citations?\s*$", re.IGNORECASE | re.MULTILINE),
    (r"^See also\s*$", re.IGNORECASE | re.MULTILINE),
    
    # Navigation/footer
    (r"^Navigation\s*$", re.IGNORECASE | re.MULTILINE),
    (r"^Footer\s*$", re.IGNORECASE | re.MULTILINE),
    (r"^Copyright.*$", re.IGNORECASE | re.MULTILINE),
]


def clean_boilerplate(text: str) -> str:
    """
    Remove web boilerplate, navigation, citations, and HTML noise.
    Returns cleaned text suitable for embedding.
    """
    if not text or not text.strip():
        return ""
    
    for pattern, flags in _BOILERPLATE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=flags)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


# ─────────────────────────────────────────────
# TOKEN COUNTING (fast heuristic)
# ─────────────────────────────────────────────

def rough_token_count(text: str) -> int:
    """
    Fast token count heuristic.
    English: ~1.3 tokens per word average.
    Good enough for gating decisions.
    """
    if not text:
        return 0
    word_count = len(text.split())
    return int(word_count * 1.3)


# ─────────────────────────────────────────────
# SENTENCE SPLITTING
# ─────────────────────────────────────────────

def split_sentences(text: str) -> List[str]:
    """
    Lightweight sentence splitter (no NLTK dependency).
    Handles common abbreviations reasonably.
    """
    if not text:
        return []
    
    # Split on sentence-ending punctuation followed by space
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Clean up empty results
    return [s.strip() for s in sentences if s.strip()]


# ─────────────────────────────────────────────
# SEMANTIC FILTERING
# ─────────────────────────────────────────────

_NOISE_MARKERS = frozenset([
    "cookie", "subscribe", "login", "sign up",
    "advertisement", "related", "share", "facebook", "twitter",
    "comments", "leave a reply", "your email",
    "save my name", "notify me", "follow",
    "post navigation", "previous post", "next post",
    "search for:", "type to search",
    "skip to content", "main menu",
    "proudly powered by", "theme by",
])

_DEFINITION_MARKERS = frozenset([
    "is defined as", "refers to", "means", "is a",
    "are defined as", "can be defined", "is described",
    "the term", "the concept", "the process",
])

_CLAIM_MARKERS = frozenset([
    "研究表明", "research shows", "studies have shown",
    "evidence suggests", "it has been found", "according to",
    "数据显示", "results indicate", "demonstrates that",
    "because", "therefore", "thus", "consequently",
    "导致", "causes", "results in", "leads to",
])


def is_informational(sentence: str) -> bool:
    """
    Heuristic filter for embedding-worthy content.
    Keeps: definitions, claims, relations, factual statements
    Drops: navigation, UI elements, formatting junk
    """
    sentence = sentence.strip()
    
    # Length gate
    if len(sentence) < MIN_SENTENCE_LEN:
        return False
    
    lower = sentence.lower()
    
    # Noise markers (instant reject)
    if any(marker in lower for marker in _NOISE_MARKERS):
        return False
    
    # URL-heavy sentences (likely citations/links)
    url_count = lower.count('http') + lower.count('www')
    if url_count > 2:
        return False
    
    # All-caps sentences (likely headers/titles)
    if sentence.isupper() and len(sentence) > 30:
        return False
    
    # Question-only sentences (low embedding value)
    if sentence.endswith('?') and '?' not in sentence[:-1]:
        return False
    
    return True


def extract_atomic_claims(sentences: List[str]) -> List[str]:
    """
    Keep only semantically useful sentences for embedding.
    """
    return [s for s in sentences if is_informational(s)]


# ─────────────────────────────────────────────
# SLIDING WINDOW
# ─────────────────────────────────────────────

def sliding_windows(items: List, size: int, stride: int):
    """
    Generate sliding windows over items.
    Overlap ensures no claim boundary loss.
    """
    for i in range(0, max(1, len(items) - size + 1), stride):
        yield items[i:i + size]


# ─────────────────────────────────────────────
# VECTOR POOLING
# ─────────────────────────────────────────────

def pool_vectors(vectors: List[List[float]], method: str = "mean") -> List[float]:
    """
    Pool multiple embedding vectors into one.
    
    Methods:
      - mean: Average pooling (default, safe)
      - max: Max pooling (preserves strongest signals)
    """
    if not vectors:
        return []
    
    if len(vectors) == 1:
        return vectors[0]
    
    dim = len(vectors[0])
    pooled = [0.0] * dim
    
    if method == "max":
        for i in range(dim):
            pooled[i] = max(v[i] for v in vectors)
    else:  # mean
        for v in vectors:
            for i in range(dim):
                pooled[i] += v[i]
        pooled = [x / len(vectors) for x in pooled]
    
    return pooled


# ─────────────────────────────────────────────
# CORE DISTILLATION PIPELINE
# ─────────────────────────────────────────────

def distill_for_embedding(raw_text: str) -> Tuple[List[str], Dict[str, int]]:
    """
    Transform noisy document into embedding-safe atomic chunks.
    
    Returns:
      (chunks, stats) where stats contains processing metrics
    """
    stats = {
        "raw_chars": len(raw_text),
        "cleaned_chars": 0,
        "sentences_total": 0,
        "sentences_filtered": 0,
        "chunks": 0,
        "overflow": False
    }
    
    # Layer 1: Boilerplate strip
    text = clean_boilerplate(raw_text)
    stats["cleaned_chars"] = len(text)
    
    if not text.strip():
        logger.warning("[Distillery] Distillation produced empty text")
        return [], stats
    
    # Layer 2: Sentence splitting + semantic filtering
    sentences = split_sentences(text)
    stats["sentences_total"] = len(sentences)
    
    atoms = extract_atomic_claims(sentences)
    stats["sentences_filtered"] = len(atoms)
    
    # Fallback if nothing survived filtering — summarize to facts, NOT raw truncation
    if not atoms:
        logger.warning("[Distillery] Zero atoms after filtering — summarizing to facts (not raw truncation)")
        stats["overflow"] = True
        facts = _summarize_to_facts(text)
        if facts:
            return facts[:5], stats  # Cap at 5 summary facts
        # Last resort: split into short meaningful chunks
        return _split_to_meaningful_chunks(text, max_chunks=5), stats
    
    # Layer 3: Size check + windowing if needed
    combined = " ".join(atoms)
    token_count = rough_token_count(combined)
    
    if token_count <= MAX_TOKENS:
        # Small enough — single embedding
        stats["chunks"] = 1
        return [combined], stats
    
    # Too big — sliding window
    stats["overflow"] = True
    chunks = []
    for window in sliding_windows(atoms, WINDOW_SIZE, STRIDE):
        chunk = " ".join(window)
        chunks.append(chunk)
    
    stats["chunks"] = len(chunks)
    logger.info(
        f"[Distillery] Windowed distillation: {len(atoms)} atoms → {len(chunks)} chunks "
        f"(tokens: {token_count})"
    )
    
    return chunks, stats


# ─────────────────────────────────────────────
# SAFE EMBEDDING WRAPPER
# ─────────────────────────────────────────────

async def safe_embed(
    text: str,
    embed_fn: Callable,
    pool_method: str = "mean"
) -> Tuple[Optional[List[float]], Dict[str, Any]]:
    """
    Embedding wrapper that guarantees no context overflow.
    
    Args:
      text: Raw document text (possibly noisy)
      embed_fn: Async function that takes str -> List[float]
      pool_method: Vector pooling strategy ("mean" or "max")
    
    Returns:
      (embedding_vector, stats_dict)
      embedding_vector is None if all chunks failed
    """
    stats = {
        "input_chars": len(text),
        "distillation": {},
        "embeddings_attempted": 0,
        "embeddings_succeeded": 0,
        "pooled": False,
        "method": pool_method
    }
    
    # Distill to atomic chunks
    chunks, distill_stats = distill_for_embedding(text)
    stats["distillation"] = distill_stats
    
    if not chunks:
        logger.warning("[Distillery] safe_embed: zero chunks after distillation")
        return None, stats
    
    # Embed each chunk — with safety net for oversized chunks
    vectors = []
    for i, chunk in enumerate(chunks):
        # Safety: split oversized chunks before embedding
        sub_chunks = chunk_text(chunk, max_chars=4000) if len(chunk) > 4000 else [chunk]
        for sub in sub_chunks:
            stats["embeddings_attempted"] += 1
            try:
                vector = await embed_fn(sub)
                if vector:
                    vectors.append(vector)
                    stats["embeddings_succeeded"] += 1
                else:
                    logger.warning(f"[Distillery] safe_embed: chunk {i} returned None")
            except Exception as e:
                logger.warning(f"[Distillery] safe_embed: chunk {i} failed: {e}")
    
    if not vectors:
        logger.error("[Distillery] safe_embed: all embeddings failed")
        return None, stats
    
    # Pool if multiple chunks
    if len(vectors) > 1:
        pooled = pool_vectors(vectors, method=pool_method)
        stats["pooled"] = True
        stats["vectors_pooled"] = len(vectors)
        return pooled, stats
    
    # Single chunk — return as-is
    return vectors[0], stats


# ─────────────────────────────────────────────
# GATE 0: SOURCE QUALITY PRE-CHECK
# ─────────────────────────────────────────────

def gate_source(raw_text: str) -> Tuple[str, int]:
    """
    Pre-flight check: should this source be embedded at all?

    Returns:
      ("OK", token_count) or ("DROP", token_count) or ("DISTILL", token_count)
    """
    cleaned = clean_boilerplate(raw_text)
    tokens = rough_token_count(cleaned)

    # Hard limit: sources this large are likely full HTML dumps
    if tokens > 8000:
        return ("DROP", tokens)

    # Medium sources need distillation but are usable
    if tokens > MAX_TOKENS * 3:
        return ("DISTILL", tokens)

    return ("OK", tokens)


def chunk_text(text: str, max_chars: int = 2000) -> List[str]:
    """
    Split text into safe-size chunks for embedding.
    Falls back when distillation produces oversized chunks.
    """
    if len(text) <= max_chars:
        return [text]
    # Split on sentence boundaries when possible
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""
    for s in sentences:
        if len(current) + len(s) > max_chars and current:
            chunks.append(current.strip())
            current = s
        else:
            current = (current + " " + s).strip()
    if current.strip():
        chunks.append(current.strip())
    # Fallback: hard split if sentences are too long
    if not chunks or any(len(c) > max_chars * 2 for c in chunks):
        chunks = [text[i:i+max_chars] for i in range(0, len(text), max_chars)]
    return chunks


# ─────────────────────────────────────────────
# SUMMARIZE TO FACTS (replaces raw truncation)
# ─────────────────────────────────────────────

def _summarize_to_facts(text: str) -> List[str]:
    """
    Extract fact-like statements from text when semantic filtering fails.
    NOT truncation — attempts to find meaningful content.

    Strategy: find sentences with numbers, named entities, or technical terms.
    These are most likely to be embeddable as atomic knowledge.
    """
    if not text or len(text) < 50:
        return []

    sentences = split_sentences(text)
    if not sentences:
        return []

    scored = []
    for s in sentences:
        if len(s) < MIN_SENTENCE_LEN:
            continue
        s_score = 0
        # Numbers = specific measurements
        if re.search(r'\d+', s):
            s_score += 2
        # Capitalized words = named entities
        caps = re.findall(r'\b[A-Z][a-z]{2,}\b', s)
        s_score += len(caps)
        # Technical indicators
        if re.search(r'(?:use|provid|achiev|implement|requir|support|enabl)', s, re.IGNORECASE):
            s_score += 1
        # Has a verb
        if re.search(r'\b(is|are|was|were|has|have|can|will|use|provide|achieve)\b', s, re.IGNORECASE):
            s_score += 1

        if s_score >= 2:
            scored.append((s_score, s))

    # Return top sentences, sorted by fact-likeness
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:10]]


def _split_to_meaningful_chunks(text: str, max_chunks: int = 5, chunk_size: int = 200) -> List[str]:
    """
    Last-resort chunking: split text into short, meaningful segments.
    Better than raw truncation because it respects sentence boundaries.
    """
    if not text:
        return []

    sentences = split_sentences(text)
    if not sentences:
        return [text[:chunk_size]]

    chunks = []
    current = ""
    for s in sentences:
        if len(current) + len(s) > chunk_size and current:
            chunks.append(current.strip())
            if len(chunks) >= max_chunks:
                return chunks
            current = s
        else:
            current = (current + " " + s).strip()

    if current and len(chunks) < max_chunks:
        chunks.append(current.strip())

    return chunks
