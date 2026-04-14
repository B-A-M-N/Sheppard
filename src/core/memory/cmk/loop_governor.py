"""
cmk/loop_governor.py — Breaks attractor loops at 3 levels.

Enforces:
  1. Retrieval-level anti-loop — diversity enforcement (max 2 atoms per cluster)
  2. Context compression — non-redundant evidence pack before LLM
  3. Output novelty gate — reject outputs that don't add new information
  4. Hard stop rule — enforce MAX_TOKENS/CLUSTERS/SENTENCES
  5. No re-explanation rule — every sentence must introduce new atomic fact
  6. Semantic memory decay — repeated clusters lose retrieval weight
  7. Cross-session loop detection — track if same concepts recur across queries

This is what turns "structured chat" into a stable cognitive system.
"""

import logging
import time
import hashlib
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from .types import CMKAtom, Concept

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Configuration constants
# ──────────────────────────────────────────────────────────────

MAX_ATOMS_PER_CLUSTER = 2
MAX_CLUSTERS_IN_RESPONSE = 3
MAX_TOTAL_SENTENCES = 6
MAX_TOKENS_PER_CLUSTER = 40  # ~2 sentences
NOVELTY_SIMILARITY_THRESHOLD = 0.92
SEMANTIC_DECAY_FACTOR = 0.7
LOOP_WINDOW = 10  # Track last 10 queries for loop detection
LOOP_SIMILARITY_THRESHOLD = 0.85


# ──────────────────────────────────────────────────────────────
# 1. Retrieval-level anti-loop — diversity enforcement
# ──────────────────────────────────────────────────────────────

def diversify_retrieval(
    atoms: List[CMKAtom],
    scores: Optional[List[float]] = None,
    max_per_cluster: int = MAX_ATOMS_PER_CLUSTER,
) -> Tuple[List[CMKAtom], List[float]]:
    """
    Enforce diversity in retrieval results.

    Caps atoms per semantic cluster to prevent "same idea repeated 10 ways"
    from feeding the model.

    Args:
        atoms: Retrieved atoms (may have cluster assignments in metadata)
        scores: Optional relevance scores
        max_per_cluster: Max atoms to keep per cluster

    Returns:
        (diversified_atoms, diversified_scores)
    """
    if scores is None:
        scores = [1.0] * len(atoms)

    # Group atoms by cluster
    clusters: Dict[str, List[Tuple[CMKAtom, float]]] = defaultdict(list)

    for atom, score in zip(atoms, scores):
        # Use topic_id or atom_type as cluster proxy if no explicit cluster
        cluster_id = _get_cluster_id(atom)
        clusters[cluster_id].append((atom, score))

    # Sort each cluster by score, keep top N
    diversified_atoms = []
    diversified_scores = []

    for cluster_id in sorted(clusters.keys()):
        cluster_items = sorted(clusters[cluster_id], key=lambda x: x[1], reverse=True)
        for atom, score in cluster_items[:max_per_cluster]:
            diversified_atoms.append(atom)
            diversified_scores.append(score)

    removed = len(atoms) - len(diversified_atoms)
    if removed > 0:
        logger.debug(f"[loop_governor] Diversified retrieval: removed {removed} redundant atoms")

    return diversified_atoms, diversified_scores


def _get_cluster_id(atom: CMKAtom) -> str:
    """Get cluster identifier for an atom."""
    # Prefer explicit metadata
    meta = atom.chroma_metadata
    if meta.get("cluster_id"):
        return str(meta["cluster_id"])

    # Fallback: use topic + type as cluster proxy
    return f"{atom.topic_id or 'default'}:{atom.atom_type}"


# ──────────────────────────────────────────────────────────────
# 2. Context compression — non-redundant evidence pack
# ──────────────────────────────────────────────────────────────

@dataclass
class CompressedContext:
    """
    Collapsed, non-redundant context ready for LLM injection.

    Instead of 30 similar atoms, produces:
      - Top 3 clusters
      - 2 unique atoms per cluster
      - One-line label per cluster
    """
    clusters: List[Dict[str, Any]] = field(default_factory=list)
    total_atoms_before: int = 0
    total_atoms_after: int = 0
    compression_ratio: float = 0.0

    def to_prompt_text(self) -> str:
        """Format as LLM-readable context."""
        if not self.clusters:
            return "INSUFFICIENT GROUNDED DATA"

        sections = []
        for i, cluster in enumerate(self.clusters, 1):
            label = cluster.get("summary_hint", f"Cluster {i}")
            sections.append(f"### {label}")
            for atom in cluster.get("atoms", []):
                atom_id = atom.id if hasattr(atom, 'id') else ""
                text = atom.content if hasattr(atom, 'content') else str(atom)
                sections.append(f"- {text} [{atom_id}]")

        return "\n".join(sections)


def compress_context(
    atoms: List[CMKAtom],
    scores: Optional[List[float]] = None,
    max_clusters: int = MAX_CLUSTERS_IN_RESPONSE,
    max_per_cluster: int = MAX_ATOMS_PER_CLUSTER,
) -> CompressedContext:
    """
    Collapse redundant evidence into a compressed, non-repetitive context.

    Args:
        atoms: Evidence atoms
        scores: Optional relevance scores
        max_clusters: Maximum clusters to include
        max_per_cluster: Maximum atoms per cluster

    Returns:
        CompressedContext ready for LLM injection
    """
    if scores is None:
        scores = [1.0] * len(atoms)

    # First diversify
    diversified, div_scores = diversify_retrieval(atoms, scores, max_per_cluster)

    # Group by cluster
    clusters: Dict[str, List[Tuple[CMKAtom, float]]] = defaultdict(list)
    for atom, score in zip(diversified, div_scores):
        cluster_id = _get_cluster_id(atom)
        clusters[cluster_id].append((atom, score))

    # Sort clusters by best atom score
    sorted_clusters = sorted(
        clusters.items(),
        key=lambda x: max(s for _, s in x[1]),
        reverse=True,
    )[:max_clusters]

    # Build compressed context
    cluster_entries = []
    for cluster_id, items in sorted_clusters:
        cluster_atoms = [a for a, _ in items]

        # Generate one-line label
        types = set(a.atom_type for a in cluster_atoms)
        summary_hint = " / ".join(sorted(types)) or "facts"

        cluster_entries.append({
            "id": cluster_id,
            "summary_hint": summary_hint,
            "atoms": cluster_atoms,
        })

    return CompressedContext(
        clusters=cluster_entries,
        total_atoms_before=len(atoms),
        total_atoms_after=sum(len(c["atoms"]) for c in cluster_entries),
        compression_ratio=len(atoms) / max(1, sum(len(c["atoms"]) for c in cluster_entries)),
    )


# ──────────────────────────────────────────────────────────────
# 3. Output novelty gate
# ──────────────────────────────────────────────────────────────

class NoveltyGate:
    """
    Rejects outputs that don't add new information.

    Compares new output against previous output using embedding similarity.
    If too similar → force regeneration with constraint.
    """

    def __init__(
        self,
        embedding_threshold: float = NOVELTY_SIMILARITY_THRESHOLD,
        text_threshold: float = 0.30,
    ):
        self.embedding_threshold = embedding_threshold
        self.text_threshold = text_threshold  # Lower threshold for word Jaccard
        self.previous_outputs: List[str] = []
        self.embedder = None  # Injected at runtime

    def set_embedder(self, embedder):
        """Set the embedder for similarity comparison."""
        self.embedder = embedder

    def check_novelty(self, new_text: str, previous_text: Optional[str] = None) -> Tuple[bool, float]:
        """
        Check if new output is sufficiently novel compared to previous.

        Args:
            new_text: The generated output
            previous_text: Previous output to compare against (defaults to last in history)

        Returns:
            (is_novel, similarity_score)
        """
        if not previous_text and self.previous_outputs:
            previous_text = self.previous_outputs[-1]

        if not previous_text:
            return True, 0.0  # No basis for comparison, assume novel

        # Try embedding-based similarity first
        if self.embedder:
            try:
                emb_new = self.embedder.embed(new_text)
                emb_prev = self.embedder.embed(previous_text)

                if emb_new is not None and emb_prev is not None:
                    sim = _cosine_lists(emb_new, emb_prev)
                    is_novel = sim < self.embedding_threshold
                    return is_novel, sim
            except Exception as e:
                logger.debug(f"[NoveltyGate] Embedding similarity failed: {e}")

        # Fallback: text-based Jaccard similarity (with punctuation stripped)
        import re
        words_new = set(re.findall(r'\b\w+\b', new_text.lower()))
        words_prev = set(re.findall(r'\b\w+\b', previous_text.lower()))

        if not words_new or not words_prev:
            return True, 0.0

        jaccard = len(words_new & words_prev) / len(words_new | words_prev)

        # Additional check: common keyword overlap (catches paraphrase better)
        # Count how many content words (non-stopwords) overlap
        stopwords = {'a', 'an', 'the', 'in', 'on', 'at', 'to', 'for', 'of', 'is', 'are',
                     'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do',
                     'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
                     'and', 'or', 'but', 'not', 'no', 'so', 'if', 'then', 'than', 'that',
                     'this', 'these', 'those', 'it', 'its', 'as', 'by', 'from', 'with',
                     'about', 'into', 'through', 'during', 'before', 'after', 'above',
                     'below', 'between', 'under', 'again', 'further', 'here', 'there',
                     'when', 'where', 'why', 'how', 'what', 'which', 'who', 'whom', 'all',
                     'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such',
                     'only', 'own', 'same', 'too', 'very', 'just', 'because', 'until', 'while'}

        content_new = words_new - stopwords
        content_prev = words_prev - stopwords

        if content_new and content_prev:
            content_overlap = len(content_new & content_prev) / min(len(content_new), len(content_prev))
            # Use the higher of jaccard and content_overlap as the similarity score
            sim = max(jaccard, content_overlap)
        else:
            sim = jaccard

        is_novel = sim < self.text_threshold

        return is_novel, sim

    def record_output(self, text: str):
        """Record an output for future novelty checks."""
        self.previous_outputs.append(text)

        # Keep history bounded
        if len(self.previous_outputs) > LOOP_WINDOW:
            self.previous_outputs = self.previous_outputs[-LOOP_WINDOW:]

    def get_regeneration_prompt(self) -> str:
        """Generate a constraint prompt for regeneration after repetition detected."""
        return (
            "Your previous response repeated information already provided. "
            "You MUST introduce NEW information only. "
            "Do NOT restate, rephrase, or expand on previously mentioned facts. "
            "If no new information is available, state that directly."
        )


def _cosine_lists(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two embedding lists."""
    import numpy as np
    a_np = np.array(a, dtype=float)
    b_np = np.array(b, dtype=float)
    norm_a = np.linalg.norm(a_np)
    norm_b = np.linalg.norm(b_np)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_np, b_np) / (norm_a * norm_b))


# ──────────────────────────────────────────────────────────────
# 4. Hard stop rule
# ──────────────────────────────────────────────────────────────

@dataclass
class StopCondition:
    """Result of stop condition check."""
    should_stop: bool
    reason: str
    sentences_used: int = 0
    clusters_used: int = 0


def check_hard_stop(
    response_text: str,
    clusters_in_context: int = 0,
    max_sentences: int = MAX_TOTAL_SENTENCES,
    max_clusters: int = MAX_CLUSTERS_IN_RESPONSE,
) -> StopCondition:
    """
    Enforce hard stop on response length and scope.

    Args:
        response_text: Generated response
        clusters_in_context: Number of clusters in the evidence
        max_sentences: Maximum sentences allowed
        max_clusters: Maximum clusters to cover

    Returns:
        StopCondition with decision
    """
    # Count sentences
    sentences = _count_sentences(response_text)

    # Check sentence limit
    if sentences > max_sentences:
        return StopCondition(
            should_stop=True,
            reason=f"exceeded_sentence_limit: {sentences}/{max_sentences}",
            sentences_used=sentences,
            clusters_used=clusters_in_context,
        )

    # Check cluster coverage (heuristic: more than max_clusters distinct topics = too broad)
    if clusters_in_context > max_clusters:
        return StopCondition(
            should_stop=True,
            reason=f"exceeded_cluster_coverage: {clusters_in_context}/{max_clusters}",
            sentences_used=sentences,
            clusters_used=clusters_in_context,
        )

    return StopCondition(
        should_stop=False,
        reason="within_limits",
        sentences_used=sentences,
        clusters_used=clusters_in_context,
    )


def _count_sentences(text: str) -> int:
    """Count sentences in text (simple heuristic)."""
    import re
    # Split on sentence-ending punctuation
    sentences = re.split(r'[.!?]+', text)
    # Filter empty/whitespace-only
    return len([s for s in sentences if s.strip()])


def truncate_to_limit(text: str, max_sentences: int = MAX_TOTAL_SENTENCES) -> str:
    """Truncate text to max_sentences."""
    import re
    sentences = re.split(r'([.!?]+)', text)

    result = []
    sentence_count = 0
    i = 0
    while i < len(sentences) and sentence_count < max_sentences:
        segment = sentences[i].strip()
        if segment:
            result.append(segment)
            # Check if next segment is punctuation
            if i + 1 < len(sentences) and sentences[i + 1].strip() in {'.', '!', '?', '.!', '?!'}:
                result.append(sentences[i + 1])
                i += 1
            sentence_count += 1
        i += 1

    return ''.join(result).strip()


# ──────────────────────────────────────────────────────────────
# 5. No re-explanation enforcement
# ──────────────────────────────────────────────────────────────

def detect_sentence_repetition(response_text: str, threshold: float = 0.5) -> List[int]:
    """
    Detect sentences within the response that repeat earlier ideas.

    Uses word-level Jaccard overlap to find sentences expressing the same concept.

    Args:
        response_text: The full response text
        threshold: Word Jaccard overlap threshold for considering sentences as repetition

    Returns:
        List of sentence indices that are repetitive
    """
    import re
    sentences = [s.strip() for s in re.split(r'[.!?]+', response_text) if s.strip()]

    if len(sentences) < 2:
        return []

    repetitive_indices = []

    for i in range(1, len(sentences)):
        current_words = set(sentences[i].lower().split())
        for j in range(i):
            if j in repetitive_indices:
                continue
            prev_words = set(sentences[j].lower().split())

            if not current_words or not prev_words:
                continue

            overlap = len(current_words & prev_words) / min(len(current_words), len(prev_words))
            if overlap > threshold:
                repetitive_indices.append(i)
                break

    return repetitive_indices


def _get_ngrams(text: str, n: int = 3) -> set:
    """Get character n-grams from text."""
    words = text.lower().split()
    if len(words) < n:
        return set(text.lower())
    return set(" ".join(words[i:i+n]) for i in range(len(words) - n + 1))


# ──────────────────────────────────────────────────────────────
# 6. Semantic memory decay
# ──────────────────────────────────────────────────────────────

class SemanticDecayTracker:
    """
    Tracks cluster reuse and applies decay to prevent long-run looping.

    If the same cluster appears repeatedly across queries, its retrieval
    weight is reduced so other clusters get a chance.
    """

    def __init__(self, decay_factor: float = SEMANTIC_DECAY_FACTOR, window: int = LOOP_WINDOW):
        self.decay_factor = decay_factor
        self.window = window
        self.cluster_usage: Dict[str, List[float]] = defaultdict(list)  # cluster_id → [timestamps]

    def record_cluster_access(self, cluster_id: str, timestamp: Optional[float] = None):
        """Record that a cluster was accessed."""
        ts = timestamp or time.time()
        self.cluster_usage[cluster_id].append(ts)

        # Prune old entries
        cutoff = ts - (self.window * 3600)  # Window in hours
        self.cluster_usage[cluster_id] = [
            t for t in self.cluster_usage[cluster_id] if t > cutoff
        ]

    def get_decay_weight(self, cluster_id: str) -> float:
        """
        Get the decay weight for a cluster.

        Returns 1.0 for fresh clusters, decaying toward 0.0 for overused ones.
        """
        usages = self.cluster_usage.get(cluster_id, [])
        count = len(usages)

        if count <= 1:
            return 1.0

        # Exponential decay: each additional usage multiplies by decay_factor
        return self.decay_factor ** (count - 1)

    def apply_decay_to_atoms(self, atoms: List[CMKAtom]) -> List[Tuple[CMKAtom, float]]:
        """
        Apply decay weights to atoms based on their cluster usage.

        Returns:
            List of (atom, decay_weight) tuples
        """
        result = []
        for atom in atoms:
            cluster_id = _get_cluster_id(atom)
            weight = self.get_decay_weight(cluster_id)
            result.append((atom, weight))
        return result

    def get_stats(self) -> Dict[str, Any]:
        """Get decay tracker statistics."""
        return {
            "tracked_clusters": len(self.cluster_usage),
            "overused_clusters": sum(
                1 for usages in self.cluster_usage.values()
                if len(usages) > 3
            ),
            "avg_decay_weight": sum(
                self.get_decay_weight(cid)
                for cid in self.cluster_usage
            ) / max(1, len(self.cluster_usage)),
        }


# ──────────────────────────────────────────────────────────────
# 7. Cross-session loop detection
# ──────────────────────────────────────────────────────────────

class CrossSessionLoopDetector:
    """
    Detects if the same concepts recur across multiple queries.

    If the user keeps asking about the same topic and getting similar answers,
    the system should recognize this and either:
      - Provide a fundamentally different angle
      - State that the topic has been exhausted
    """

    def __init__(self, window: int = LOOP_WINDOW, threshold: float = LOOP_SIMILARITY_THRESHOLD):
        self.window = window
        self.threshold = threshold
        self.query_history: List[Dict[str, Any]] = []
        self.cluster_history: List[Set[str]] = []
        self.response_hashes: List[str] = []

    def record_interaction(self, query: str, cluster_ids: Set[str], response_text: str):
        """Record a query-response interaction for loop detection."""
        self.query_history.append({
            "query": query,
            "timestamp": time.time(),
            "response_hash": hashlib.sha256(response_text.encode()).hexdigest()[:16],
        })
        self.cluster_history.append(cluster_ids)

        # Prune old entries
        if len(self.query_history) > self.window:
            self.query_history = self.query_history[-self.window:]
            self.cluster_history = self.cluster_history[-self.window:]

    def detect_loop(self, current_query: str, current_clusters: Set[str]) -> Tuple[bool, str]:
        """
        Check if current query is looping on previous interactions.

        Args:
            current_query: Current user query
            current_clusters: Clusters being retrieved for this query

        Returns:
            (is_looping, reason)
        """
        if not self.query_history:
            return False, ""

        # Check query similarity
        for past in self.query_history:
            query_sim = _text_similarity(current_query, past["query"])
            if query_sim > self.threshold:
                # Same query, check if same clusters
                past_clusters = next(
                    (c for i, c in enumerate(self.cluster_history)
                     if i < len(self.query_history) and self.query_history[i]["query"] == past["query"]),
                    set(),
                )
                cluster_overlap = len(current_clusters & past_clusters) / max(1, len(current_clusters | past_clusters))

                if cluster_overlap > 0.7:
                    return True, f"repeated_query_same_clusters: {query_sim:.2f} query similarity, {cluster_overlap:.2f} cluster overlap"

        # Check cluster repetition (different queries, same clusters)
        recent_clusters = self.cluster_history[-3:]
        if all(len(c & current_clusters) / max(1, len(c)) > 0.8 for c in recent_clusters if c):
            return True, "cluster_loop: same clusters accessed across different queries"

        return False, ""

    def get_loop_breaking_suggestion(self) -> str:
        """Generate a suggestion when a loop is detected."""
        return (
            "This topic has been explored extensively in recent interactions. "
            "The available knowledge on this angle may be exhausted. "
            "Consider asking about a specific sub-topic or different aspect."
        )


def _text_similarity(a: str, b: str) -> float:
    """Simple text similarity via Jaccard overlap of words."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


# ──────────────────────────────────────────────────────────────
# 8. The Loop Governor — single module that ties everything together
# ──────────────────────────────────────────────────────────────

@dataclass
class GovernorDecision:
    """Result of governor evaluation."""
    action: str  # "proceed", "truncate", "regenerate", "stop", "warn"
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


class LoopGovernor:
    """
    Single module that enforces all loop-breaking constraints.

    Pipeline:
      1. Diversify retrieval
      2. Compress context
      3. Check for cross-session loops
      4. Apply semantic decay
      5. After generation: check novelty, detect sentence repetition, enforce hard stop
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Args:
            config: Optional configuration overrides
        """
        self.config = config or {}
        self.max_per_cluster = self.config.get("max_per_cluster", MAX_ATOMS_PER_CLUSTER)
        self.max_clusters = self.config.get("max_clusters", MAX_CLUSTERS_IN_RESPONSE)
        self.max_sentences = self.config.get("max_sentences", MAX_TOTAL_SENTENCES)

        # Sub-modules
        self.novelty_gate = NoveltyGate()
        self.decay_tracker = SemanticDecayTracker()
        self.loop_detector = CrossSessionLoopDetector()

        # State
        self.last_response: Optional[str] = None
        self.last_clusters: Set[str] = set()

    def pre_generate(
        self,
        atoms: List[CMKAtom],
        scores: Optional[List[float]] = None,
        user_query: str = "",
    ) -> Tuple[CompressedContext, List[GovernorDecision]]:
        """
        Pre-generation pipeline: diversify, compress, check loops.

        Args:
            atoms: Retrieved atoms
            scores: Optional relevance scores
            user_query: Current user query

        Returns:
            (compressed_context, decisions)
        """
        decisions = []

        # 1. Check cross-session loops
        cluster_ids = set(_get_cluster_id(a) for a in atoms)
        is_looping, loop_reason = self.loop_detector.detect_loop(user_query, cluster_ids)
        if is_looping:
            decisions.append(GovernorDecision(
                action="warn",
                reason=loop_reason,
                details={"suggestion": self.loop_detector.get_loop_breaking_suggestion()},
            ))

        # 2. Apply semantic decay
        decayed_atoms = []
        decayed_scores = []
        if scores:
            for atom, score in zip(atoms, scores):
                cluster_id = _get_cluster_id(atom)
                decay = self.decay_tracker.get_decay_weight(cluster_id)
                decayed_atoms.append(atom)
                decayed_scores.append(score * decay)
        else:
            decayed_atoms = atoms
            decayed_scores = None

        # 3. Diversify retrieval
        diversified, div_scores = diversify_retrieval(
            decayed_atoms, decayed_scores, self.max_per_cluster
        )

        # 4. Compress context
        compressed = compress_context(
            diversified, div_scores, self.max_clusters, self.max_per_cluster
        )

        # Record cluster access for decay tracking
        for atom in diversified:
            self.decay_tracker.record_cluster_access(_get_cluster_id(atom))

        self.last_clusters = cluster_ids

        if compressed.compression_ratio > 3:
            decisions.append(GovernorDecision(
                action="proceed",
                reason=f"high_compression: {compressed.compression_ratio:.1f}x",
                details={"atoms_before": compressed.total_atoms_before, "atoms_after": compressed.total_atoms_after},
            ))

        return compressed, decisions

    def post_generate(
        self,
        response_text: str,
        user_query: str = "",
    ) -> List[GovernorDecision]:
        """
        Post-generation evaluation: novelty check, repetition detection, hard stop.

        Args:
            response_text: Generated response
            user_query: Original query

        Returns:
            List of governor decisions
        """
        decisions = []

        # 1. Check novelty against last response
        is_novel, novelty_sim = self.novelty_gate.check_novelty(response_text, self.last_response)
        if not is_novel:
            decisions.append(GovernorDecision(
                action="regenerate",
                reason=f"low_novelty: similarity={novelty_sim:.3f} (threshold={self.novelty_gate.embedding_threshold})",
                details={"regeneration_prompt": self.novelty_gate.get_regeneration_prompt()},
            ))

        # 2. Detect sentence-level repetition
        repetitive_sentences = detect_sentence_repetition(response_text)
        if repetitive_sentences:
            decisions.append(GovernorDecision(
                action="warn",
                reason=f"sentence_repetition: {len(repetitive_sentences)} repetitive sentences detected",
                details={"repetitive_indices": repetitive_sentences},
            ))

        # 3. Hard stop check
        stop = check_hard_stop(response_text, len(self.last_clusters), self.max_sentences, self.max_clusters)
        if stop.should_stop:
            decisions.append(GovernorDecision(
                action="truncate",
                reason=stop.reason,
                details={"sentences_used": stop.sentences_used, "max": self.max_sentences},
            ))
            response_text = truncate_to_limit(response_text, self.max_sentences)

        # Record for future checks
        self.novelty_gate.record_output(response_text)
        self.last_response = response_text
        self.loop_detector.record_interaction(user_query, self.last_clusters, response_text)

        if not decisions:
            decisions.append(GovernorDecision(
                action="proceed",
                reason="all_checks_passed",
            ))

        return decisions

    def get_stats(self) -> Dict[str, Any]:
        """Get governor statistics."""
        return {
            "decay_tracker": self.decay_tracker.get_stats(),
            "novelty_history_size": len(self.novelty_gate.previous_outputs),
            "loop_history_size": len(self.loop_detector.query_history),
        }
