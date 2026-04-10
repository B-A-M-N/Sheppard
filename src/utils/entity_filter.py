"""
entity_filter.py — Cognitive Filter: domain-agnostic structural entity classification.

Filters *reusability in reasoning*, not words.
No subject-matter knowledge. No keyword lists. No domain rules.

Tiers:
  EXPANDABLE  → Frontier expansion seeds (stable, self-contained concepts)
  CONTEXTUAL  → stored for reference only (datasets, tools, locations)
  NOISE       → dropped (fragments, metadata, artifacts)
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ── Structural artifact indicators (NOT domain knowledge) ──
_ARTIFACT_PATTERNS = {
    "doi:", "isbn:", "issn:", "pmid:", "pmcid:", "arxiv:",
    "vol.", "no.", "pp.", "pg.", "cf.", "fig.", "eq.", "sec.",
    "click here", "read more", "view full", "all rights reserved",
    "powered by", "terms of use", "privacy policy",
    "contact us", "subscribe", "follow us",
}


def _is_artifact_fragment(entity):
    """Reject document/web plumbing via structural patterns only."""
    lower = entity.lower()
    for pattern in _ARTIFACT_PATTERNS:
        if pattern in lower:
            return True
    if any(c in entity for c in ("://", "www.")):
        return True
    if "@" in entity:
        return True
    if len(entity) > 3 and entity.startswith("10.") and entity[3:5].isdigit():
        return True
    stripped = entity.replace(" ", "").replace("-", "").replace(",", "")
    if stripped.isdigit():
        return True
    if len(entity) == 1 and entity.isupper():
        return True
    return False


def _is_generic_singleton(entity):
    """Reject single-token entity that is too generic to expand."""
    words = entity.split()
    if len(words) != 1:
        return False
    w = words[0].lower()
    if len(w) <= 3:
        return True
    if w in {
        "the", "a", "an", "of", "in", "on", "at", "to", "for",
        "and", "or", "but", "is", "are", "was", "were", "be",
        "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "can", "could", "may", "might",
        "shall", "should", "must", "need", "dare", "ought",
        "used", "about", "above", "across", "after", "against",
        "along", "among", "around", "before", "behind", "below",
        "beneath", "beside", "between", "beyond", "by", "down",
        "during", "except", "from", "into", "like", "near",
        "off", "onto", "out", "outside", "over", "past",
        "since", "through", "till", "toward", "under", "until",
        "up", "upon", "with", "within", "without",
        "thing", "things", "stuff", "way", "ways",
        "one", "ones", "part", "parts",
    }:
        return True
    return False


def _is_language_list(entity):
    """Detect language-list extraction artifacts."""
    words = entity.lower().split()
    if len(words) < 3:
        return False
    known = {
        "english", "spanish", "portuguese", "french", "german",
        "italian", "dutch", "russian", "chinese", "japanese",
        "korean", "arabic", "hindi", "bengali", "turkish",
        "polish", "swedish", "norwegian", "danish", "finnish",
        "greek", "hebrew", "thai", "vietnamese", "indonesian",
        "malay", "tagalog", "swahili", "amharic", "latin",
        "czech", "romanian", "hungarian", "ukrainian", "persian",
        "urdu", "tamil", "telugu", "marathi", "gujarati",
    }
    match_count = sum(1 for w in words if w in known)
    return match_count >= 3


def _conceptual_suffix_score(entity):
    """Bonus for morphological markers of abstract concepts."""
    score = 0.0
    suffixes = {
        "ing", "tion", "sion", "ment", "ence", "ance",
        "ity", "ness", "ology", "graphy", "metry",
    }
    for w in entity.lower().split():
        for sfx in suffixes:
            if w.endswith(sfx) and len(w) > len(sfx) + 1:
                score += 0.5
                break
    return score


def _is_camel_case(token):
    """CamelCase via pure string ops. Requires 2+ uppercase and mixed case."""
    if not token or len(token) < 3:
        return False
    upper_count = sum(1 for ch in token if ch.isupper())
    has_lower = any(ch.islower() for ch in token)
    return has_lower and upper_count >= 2


def _structural_stability(entity):
    """Score based on purely structural properties."""
    score = 0.0
    words = entity.split()
    if len(words) >= 2:
        score += 2.0
    if len(words) >= 3:
        score += 1.0
    if len(words) > 6:
        score -= 2.0
    if len(entity) < 4:
        score -= 2.0
    if len(entity) > 100:
        score -= 1.0
    if entity[0].isupper() and not entity.isupper():
        score += 0.5
    if entity.isupper():
        score -= 2.0
    if _is_camel_case(entity):
        score += 1.5
    if all(w[0].isupper() for w in words if w):
        score += 1.0
    if "-" in entity and len(words) == 1:
        score += 1.0
    score += _conceptual_suffix_score(entity)
    if len(words) > 1:
        unique_ratio = len(set(w.lower() for w in words)) / len(words)
        if unique_ratio < 0.7:
            score -= 1.0
    return score


def _classify_tier(entity, cross_freq=0):
    """
    Classify entity into tier.
    cross_freq is THE Key signal: real concepts appear across multiple sources.
    Returns: "expandable" | "contextual" | "noise"
    """
    if _is_artifact_fragment(entity):
        return "noise"
    if _is_generic_singleton(entity):
        return "noise"
    if _is_language_list(entity):
        return "noise"
    if len(entity) <= 2:
        return "noise"

    if cross_freq >= 3:
        return "expandable"

    if cross_freq == 2:
        struct = _structural_stability(entity)
        if struct >= 2.0:
            return "expandable"
        return "contextual"

    # cross_freq == 1
    struct = _structural_stability(entity)
    if struct >= 3.0:
        return "contextual"
    return "noise"


def _canonicalize(entity):
    """Canonical form for deduplication. Strips determiners, singularizes."""
    words = entity.split()
    while words and words[0].lower() in {
        "the", "a", "an", "this", "that", "these", "those",
        "its", "our", "their", "his", "her", "my", "your",
    }:
        words = words[1:]
    if not words:
        return ""
    last = words[-1].lower()
    if last.endswith("ies") and len(last) > 4:
        words[-1] = words[-1][:-3] + "y"
    elif last.endswith("ses") and len(last) > 4 and not last.endswith("sses"):
        words[-1] = words[-1][:-1]
    elif last.endswith("ches") and len(last) > 5:
        words[-1] = words[-1][:-2]
    elif last.endswith("s") and not last.endswith("ss") and len(last) > 3:
        words[-1] = words[-1][:-1]
    return " ".join(words)


def _compute_cross_frequency(raw_entities):
    """Count appearances per canonical form. Proxy for cross-source stability."""
    freq = {}
    for e in raw_entities:
        canon = _canonicalize(e)
        if canon:
            freq[canon] = freq.get(canon, 0) + 1
    return freq


def _filter_and_dedup(raw_entities):
    """Full cognitive gate: cross-frequency → tier → canonicalize → only EXPANDABLE."""
    freq = _compute_cross_frequency(raw_entities)
    canonical_groups = {}
    for entity in raw_entities:
        tier = _classify_tier(entity, cross_freq=freq.get(_canonicalize(entity), 0))
        if tier == "noise":
            continue
        canon = _canonicalize(entity)
        if not canon:
            continue
        score = _structural_stability(entity)
        if canon not in canonical_groups:
            canonical_groups[canon] = []
        canonical_groups[canon].append((entity, tier, score))

    result = []
    for canon, forms in canonical_groups.items():
        expandable = [(e, s) for e, t, s in forms if t == "expandable"]
        if expandable:
            best = max(expandable, key=lambda x: x[1])
            result.append(best[0])
    return result


def _extract_entities_from_atoms(atoms):
    """
    Extract named entities from atoms for Frontier discovery.
    Pipeline: extract → structural reject → cross-frequency → tier → gate
    """
    SKIP_PREFIXES = {
        "the", "a", "an", "this", "that", "these", "those",
        "its", "our", "their", "his", "her", "my", "your",
    }

    raw_entities = []
    for atom in atoms:
        content = atom.get("text", atom.get("content", ""))
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

    return _filter_and_dedup(raw_entities)
