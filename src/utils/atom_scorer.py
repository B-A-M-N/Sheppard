"""
atom_scorer.py — Multi-Dimensional Atom Scoring

Replaces binary valid/invalid classification with a continuous
acceptance score. Enables gradient-based filtering instead of
hard thresholds that cause zero-yield cascades.

Scoring dimensions:
  - clarity: sentence structure, termination, readability
  - factual_density: information content per word
  - citation_likelihood: presence of concrete details (numbers, names, dates)
  - redundancy_penalty: similarity to already-seen content

Final score: weighted composite → accept if > 0.65
"""

import re
import math
from typing import Dict, Any, List, Optional, Set
from collections import Counter

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

WEIGHTS = {
    "clarity": 0.40,         # Up from 0.30 — structure matters most
    "factual_density": 0.30, # Up from 0.25 — information content
    "citation_likelihood": 0.10,  # DOWN from 0.25 — too punitive for non-technical text
    "redundancy_penalty": 0.20,
}

ACCEPTANCE_THRESHOLD = 0.50  # DOWN from 0.65 — realistic threshold for varied text
LOW_QUALITY_THRESHOLD = 0.25  # DOWN from 0.35 — more atoms get repair chance
REPAIR_CANDIDATE_THRESHOLD = 0.35  # Between 0.25-0.50 → attempt repair


# ─────────────────────────────────────────────
# CLARITY SCORE
# ─────────────────────────────────────────────

_SENTENCE_ENDINGS = {'.', '!', '?'}
_ACCEPTABLE_CLOSERS = {')', ']', '"', '>', '°', '%'}

_VERB_PATTERNS = [
    ' is ', ' are ', ' was ', ' were ', ' has ', ' have ', ' had ',
    ' can ', ' could ', ' will ', ' would ', ' should ', ' may ',
    ' uses ', ' used ', ' using ', ' provides ', ' achieves ',
    ' reduces ', ' increases ', ' improves ', ' shows ',
    ' demonstrates ', ' implements ', ' requires ', ' supports ',
    ' enables ', ' allows ', ' prevents ', ' detects ', ' generates ',
    ' trains ', ' trained ', ' predicts ', ' evaluates ', ' compares ',
    ' consists ', ' contains ', ' produces ', ' creates ',
    ' defines ', ' specifies ', ' establishes ', ' determines ',
]

_FUNCTION_WORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
    'would', 'can', 'could', 'shall', 'should', 'may', 'might',
    'must', 'of', 'in', 'to', 'for', 'with', 'on', 'at', 'from',
    'by', 'about', 'as', 'into', 'like', 'through', 'after',
    'over', 'between', 'out', 'against', 'during', 'without',
    'before', 'under', 'around', 'and', 'but', 'or', 'nor',
    'not', 'so', 'yet', 'both', 'either', 'neither', 'each',
    'every', 'all', 'any', 'few', 'more', 'most', 'other',
    'some', 'such', 'than', 'too', 'very', 'just', 'also',
    'that', 'which', 'who', 'whom', 'whose', 'what', 'where',
    'when', 'why', 'how', 'if', 'because', 'while', 'although',
    'it', 'its', 'this', 'that', 'these', 'those', 'i', 'you',
    'he', 'she', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
    'my', 'your', 'his', 'her', 'our', 'their', 'mine', 'yours',
}


def _has_verb(text: str) -> bool:
    text_lower = text.lower()
    return any(v in text_lower for v in _VERB_PATTERNS)


def _has_complete_ending(text: str) -> bool:
    text = text.rstrip()
    if any(text.endswith(e) for e in _SENTENCE_ENDINGS):
        return True
    if any(text.endswith(c) for c in _ACCEPTABLE_CLOSERS):
        # Check that the character before the closer is meaningful
        if len(text) > 2 and text[-2] not in (' ', '\t', '\n'):
            return True
    return False


def clarity_score(content: str) -> float:
    """
    Score 0-1 based on structural clarity.
    Factors: sentence termination, verb presence, word count, readability.
    """
    if not content or len(content) < 5:
        return 0.0

    score = 0.0
    words = content.split()
    word_count = len(words)

    # Termination (0.35 weight)
    if _has_complete_ending(content):
        score += 0.35

    # Verb presence (0.35 weight)
    if _has_verb(content):
        score += 0.35

    # Length sweet spot (0.15 weight)
    # 8-50 words is ideal for an atom
    if 8 <= word_count <= 50:
        score += 0.15
    elif 5 <= word_count < 8:
        score += 0.08
    elif word_count > 50:
        score += 0.03  # Too long — unclear boundaries

    # Lowercase ratio penalty (all caps or all lowercase = less clear)
    alpha_chars = [c for c in content if c.isalpha()]
    if alpha_chars:
        upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
        # Ideal: 5-20% uppercase (normal sentence casing)
        if 0.03 <= upper_ratio <= 0.25:
            score += 0.15
        elif 0.01 <= upper_ratio <= 0.40:
            score += 0.08

    return min(score, 1.0)


# ─────────────────────────────────────────────
# FACTUAL DENSITY SCORE
# ─────────────────────────────────────────────

def factual_density(content: str) -> float:
    """
    Score 0-1 based on information density.
    Higher ratio of content words to function words = denser.
    """
    if not content or len(content) < 10:
        return 0.0

    words = [w.lower().strip('.,;:!?()"\'') for w in content.split()]
    if not words:
        return 0.0

    content_words = [w for w in words if w and w not in _FUNCTION_WORDS]
    total_words = len(words)

    if total_words == 0:
        return 0.0

    content_ratio = len(content_words) / total_words

    # Presence of concrete details boosts density
    density_boosters = 0.0

    # Numbers (specific measurements)
    if re.search(r'\d+\.?\d*\s*(?:percent|%|ms|ms|gb|mb|tb|params|layers|epochs|accuracy|error|loss|score)', content, re.IGNORECASE):
        density_boosters += 0.2

    # Named entities (capitalized multi-word phrases)
    if re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', content):
        density_boosters += 0.15

    # Technical terms (CamelCase, hyphenated compounds)
    if re.search(r'[a-z]+[A-Z]', content) or re.search(r'[a-z]+-[a-z]+', content):
        density_boosters += 0.1

    # Quoted terms or specific concepts
    if content.count('"') >= 2 or content.count("'") >= 2:
        density_boosters += 0.05

    score = content_ratio * 0.6 + density_boosters
    return min(score, 1.0)


# ─────────────────────────────────────────────
# CITATION LIKELIHOOD SCORE
# ─────────────────────────────────────────────

def citation_likelihood(content: str) -> float:
    """
    Score 0-1 based on presence of citeable details.
    Atoms with numbers, names, dates, or specific references
    are more likely to be real, grounded claims.
    """
    if not content or len(content) < 10:
        return 0.0

    score = 0.0

    # Numeric data (measurements, percentages, counts)
    numbers = re.findall(r'\d+\.?\d*', content)
    if numbers:
        score += min(len(numbers) * 0.1, 0.3)

    # Specific technical terms (architectures, methods, tools)
    tech_indicators = [
        r'\b[A-Z][A-Za-z]*(?:Net|Net|Model|Layer|Method|Algorithm|System|Framework)\b',
        r'\b(Accuracy|Precision|Recall|F1|Loss|Error|Throughput|Latency|Params)\b',
        r'\b(Transformer|CNN|RNN|LSTM|GRU|GAN|BERT|GPT|ResNet|VGG|Attention)\b',
        r'\b(PyTorch|TensorFlow|JAX|NumPy|SciPy|Pandas)\b',
    ]
    for pattern in tech_indicators:
        if re.search(pattern, content):
            score += 0.15
            break

    # Specific version numbers or dates
    if re.search(r'v?\d+\.\d+', content) or re.search(r'\b(20\d{2}|19\d{2})\b', content):
        score += 0.1

    # Proper nouns (likely references to real entities)
    proper_nouns = re.findall(r'\b[A-Z][a-z]{2,}\b', content)
    if len(proper_nouns) >= 2:
        score += 0.15
    elif len(proper_nouns) == 1:
        score += 0.08

    # Comparative language (suggests grounded evaluation)
    if re.search(r'\b(more|less|better|worse|higher|lower|faster|slower|improved|decreased)\b', content, re.IGNORECASE):
        score += 0.1

    return min(score, 1.0)


# ─────────────────────────────────────────────
# REDUNDANCY PENALTY
# ─────────────────────────────────────────────


def _content_signature(content: str, ngram_size: int = 4) -> Set[str]:
    """
    Create a set of n-gram signatures for fuzzy matching.
    Lowercase, stripped of punctuation.
    """
    text = re.sub(r'[^\w\s]', '', content.lower())
    words = text.split()
    if len(words) < ngram_size:
        return {' '.join(words)}
    return {' '.join(words[i:i+ngram_size]) for i in range(len(words) - ngram_size + 1)}


def redundancy_score(content: str, seen_signatures: Optional[Set[str]] = None) -> float:
    """
    Score 0-1 where 1.0 = completely unique, 0.0 = exact duplicate.
    This is an INVERSE redundancy score (higher = better).
    """
    if not content:
        return 0.0

    if seen_signatures is None or not seen_signatures:
        return 1.0  # Nothing to compare against = unique

    sig = _content_signature(content)
    if not sig:
        return 0.0

    # Jaccard similarity against all seen content
    overlap = len(sig & seen_signatures)
    total = len(sig | seen_signatures)

    if total == 0:
        return 1.0

    similarity = overlap / total
    uniqueness = 1.0 - similarity

    # Exponential decay: 50% overlap → score drops sharply
    return uniqueness ** 2


# ─────────────────────────────────────────────
# COMPOSITE SCORING
# ─────────────────────────────────────────────


def score_atom(
    content: str,
    seen_signatures: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """
    Score an atom on all dimensions.

    Returns:
      {
        "score": 0.72,  # composite
        "clarity": 0.85,
        "factual_density": 0.62,
        "citation_likelihood": 0.70,
        "redundancy": 0.90,  # 1.0 = unique
        "verdict": "accept" | "repair" | "reject"
      }
    """
    clarity = clarity_score(content)
    density = factual_density(content)
    citation = citation_likelihood(content)
    redundancy = redundancy_score(content, seen_signatures)

    composite = (
        clarity * WEIGHTS["clarity"]
        + density * WEIGHTS["factual_density"]
        + citation * WEIGHTS["citation_likelihood"]
        + redundancy * WEIGHTS["redundancy_penalty"]
    )

    if composite >= ACCEPTANCE_THRESHOLD:
        verdict = "accept"
    elif composite >= LOW_QUALITY_THRESHOLD:
        verdict = "repair"
    else:
        verdict = "reject"

    return {
        "score": round(composite, 3),
        "clarity": round(clarity, 3),
        "factual_density": round(density, 3),
        "citation_likelihood": round(citation, 3),
        "redundancy": round(redundancy, 3),
        "verdict": verdict,
    }


def score_atom_batch(
    atoms: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Score a batch of atoms, tracking redundancy across the batch.
    Each atom gets scored in context of all previous atoms.

    Returns list of atoms with scoring metadata attached.
    """
    seen_sigs: Set[str] = set()
    results = []

    for atom in atoms:
        content = atom.get('text', atom.get('content', ''))
        scoring = score_atom(content, seen_sigs)

        # Update seen signatures
        sigs = _content_signature(content)
        seen_sigs.update(sigs)

        # Attach scoring to atom
        scored_atom = {**atom, "scoring": scoring}
        results.append(scored_atom)

    return results


# ─────────────────────────────────────────────
# ACCEPTANCE GATE
# ─────────────────────────────────────────────


def accept_atom(content: str, seen_signatures: Optional[Set[str]] = None) -> bool:
    """Quick acceptance check using the scoring pipeline."""
    result = score_atom(content, seen_signatures)
    return result["verdict"] != "reject"


def filter_atoms_by_score(
    atoms: List[Dict[str, Any]],
    min_score: float = ACCEPTANCE_THRESHOLD,
    max_repair_candidates: int = 20
) -> tuple:
    """
    Filter atoms by score. Returns:
      (accepted, repair_candidates, rejected)

    accepted: atoms scoring >= min_score
    repair_candidates: atoms scoring between LOW_QUALITY_THRESHOLD and min_score
    rejected: atoms scoring below LOW_QUALITY_THRESHOLD
    """
    seen_sigs: Set[str] = set()
    accepted = []
    repair_candidates = []
    rejected = []

    for atom in atoms:
        content = atom.get('text', atom.get('content', ''))
        scoring = score_atom(content, seen_sigs)
        sigs = _content_signature(content)
        seen_sigs.update(sigs)

        atom_with_score = {**atom, "scoring": scoring}

        if scoring["score"] >= min_score:
            accepted.append(atom_with_score)
        elif scoring["score"] >= LOW_QUALITY_THRESHOLD:
            if len(repair_candidates) < max_repair_candidates:
                repair_candidates.append(atom_with_score)
            else:
                rejected.append(atom_with_score)
        else:
            rejected.append(atom_with_score)

    return accepted, repair_candidates, rejected
