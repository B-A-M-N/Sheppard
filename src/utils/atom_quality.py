"""
atom_quality.py — Structural atom quality classification (no LLM, no embeddings).

Cheap local heuristics for validating atom structure.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _has_verb(text: str) -> bool:
    """Cheap heuristic: does this sentence have a verb-like word?"""
    verb_patterns = [
        ' is ', ' are ', ' was ', ' were ', ' has ', ' have ', ' had ',
        ' can ', ' could ', ' will ', ' would ', ' should ', ' may ',
        ' uses ', ' used ', ' using ', ' provides ', ' achieves ',
        ' reduces ', ' increases ', ' improves ', ' shows ',
        ' demonstrates ', ' implements ', ' requires ', ' supports ',
        ' enables ', ' allows ', ' prevents ', ' detects ', ' generates ',
        ' trains ', ' trained ', ' predicts ', ' evaluates ', ' compares ',
    ]
    text_lower = text.lower()
    return any(v in text_lower for v in verb_patterns)


def _classify_atom_quality(content: str) -> str:
    """Cheap structural validation. Returns 'VALID', 'FRAGMENT', or 'WEAK'."""
    if not content or len(content) < 20:
        return 'FRAGMENT'

    has_period = content.rstrip().endswith(('.', '!', '?', ')', ']'))
    has_v = _has_verb(content)
    wc = len(content.split())

    if has_period and has_v and wc >= 8:
        return 'VALID'
    elif not has_period or not has_v:
        return 'FRAGMENT'
    else:
        return 'WEAK'  # Has verb and termination but short


# Concepts that indicate the atom is noise or too generic to be useful
_NOISE_CONCEPTS = frozenset({
    # Function words / stopwords mistaken as concepts
    "the", "a", "an", "this", "that", "it", "they", "various", "several",
    # Generic document meta
    "article", "document", "section", "paragraph", "page", "text",
    "the article", "this article", "the document", "the paper", "this paper",
    "the section", "this section", "the study", "this study",
    # Meaningless generic labels
    "general", "overview", "introduction", "summary", "conclusion",
    "information", "content", "data", "details", "examples", "methods",
    "approach", "process", "system", "various methods", "multiple methods",
    # Navigational noise from web pages
    "click here", "read more", "learn more", "see also", "related",
    "navigation", "menu", "footer", "header", "sidebar",
    # Completely topic-neutral
    "research", "study", "analysis", "results", "findings",
})


def is_noise_concept(concept: str) -> bool:
    """Return True if the extracted concept is too generic to be useful."""
    if not concept or not concept.strip():
        return True
    normalized = concept.strip().lower()
    if normalized in _NOISE_CONCEPTS:
        return True
    # Single-character or pure numeric
    if len(normalized) <= 2:
        return True
    return False


def _structural_validation(atoms: List[Dict[str, Any]]) -> Dict[str, int]:
    """Cheap local validation — no LLM calls. Classifies each atom."""
    report = {'VALID': 0, 'FRAGMENT': 0, 'WEAK': 0}
    for atom in atoms:
        content = atom.get('text', atom.get('content', ''))
        quality = _classify_atom_quality(content)
        report[quality] += 1
    return report
