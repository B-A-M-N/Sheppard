"""
src/research/reasoning/analytical_operators.py

Analytical & Comparative Reasoning Layer — Phase 12-B.

Six deterministic, LLM-free operators that transform raw RetrievedItem atoms
into structured comparative intelligence. All operators:
  - Are pure functions: same inputs → same outputs
  - Skip silently on insufficient data (never raise, never fabricate)
  - Sort atoms by citation_key before processing for determinism

Operators:
  compare_contrast_bundle  — group by entity, find agreements/differences
  tradeoff_extraction      — classify pro/con language patterns
  method_result_pairing    — pair methodology atoms with result atoms
  consensus_divergence     — lexical clustering into consensus/divergent sets
  source_authority_weight  — score atoms by trust × level × recency
  change_detection         — detect metric changes over time
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.retrieval.models import RetrievedItem

import logging
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────

@dataclass
class AnalyticalBundle:
    """Structured output of a single analytical operator over a set of atoms."""
    operator: str               # operator name string
    atom_ids: List[str]         # citation_keys of all source atoms
    output: Any                 # operator-specific structured dict
    metadata: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "of", "at", "by", "for",
    "with", "in", "on", "to", "from", "is", "are", "was", "were", "be",
    "been", "it", "its", "this", "that", "as", "also", "has", "have", "had",
    "not", "all", "any", "so", "do", "does", "did", "will", "can", "may",
    "more", "most", "into", "out", "up", "than", "then", "their", "there",
    "over", "our", "we", "they", "he", "she", "which", "who", "what",
}

_PRO_PATTERNS = re.compile(
    r'\b(advantage|benefit|strength|pro\b|upside|positive|gain|improvement|efficient|fast|simple|easy|flexible|scalable)\b',
    re.IGNORECASE,
)
_CON_PATTERNS = re.compile(
    r'\b(disadvantage|drawback|weakness|con\b|downside|limitation|risk|slow|complex|difficult|expensive|poor|lack|issue|problem|concern)\b',
    re.IGNORECASE,
)

_NUMBER_PATTERN = re.compile(r'[\d,]+\.?\d*')


def _tokenize(text: str) -> List[str]:
    """Lowercase alphanumeric tokens, stopwords removed."""
    tokens = re.split(r'\W+', text.lower())
    return [t for t in tokens if t and t not in _STOPWORDS and len(t) > 1]


def _token_set(text: str) -> set:
    return set(_tokenize(text))


def _extract_first_number(text: str) -> Optional[float]:
    matches = _NUMBER_PATTERN.findall(text)
    for m in matches:
        cleaned = m.replace(',', '')
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                continue
    return None


def _sort_atoms(atoms: List[RetrievedItem]) -> List[RetrievedItem]:
    """Deterministic sort by citation_key."""
    return sorted(atoms, key=lambda a: a.citation_key or '')


def _entity_key(atom: RetrievedItem) -> Optional[str]:
    """Return entity grouping key from metadata, or None."""
    meta = atom.metadata or {}
    return meta.get('entity_id') or meta.get('entity') or meta.get('concept_name')


# ──────────────────────────────────────────────────────────────
# 1. compare_contrast_bundle
# ──────────────────────────────────────────────────────────────

def compare_contrast_bundle(atoms: List[RetrievedItem]) -> List[AnalyticalBundle]:
    """
    Group atoms by entity metadata key. For each group with ≥2 atoms, compute:
    - agreements: token overlap shared by ALL atoms in the group
    - differences: tokens unique to each atom vs the group intersection

    Returns a list of AnalyticalBundle (one per qualifying group).
    Returns [] if no group has ≥2 atoms or no atoms have entity metadata.
    """
    try:
        sorted_atoms = _sort_atoms(atoms)

        # Group by entity
        groups: Dict[str, List[RetrievedItem]] = defaultdict(list)
        for atom in sorted_atoms:
            key = _entity_key(atom)
            if key is not None:
                groups[key].append(atom)

        bundles = []
        for entity, group in groups.items():
            if len(group) < 2:
                continue

            token_sets = [_token_set(a.content) for a in group]

            # Agreements: tokens present in ALL atoms
            agreements = token_sets[0]
            for ts in token_sets[1:]:
                agreements = agreements & ts
            agreements = sorted(agreements)

            # Differences: tokens unique to each atom
            differences = []
            for atom, ts in zip(group, token_sets):
                unique = ts - set(agreements)
                differences.append({
                    "atom_id": atom.citation_key,
                    "unique_tokens": sorted(unique),
                })

            atom_ids = [a.citation_key for a in group]
            bundles.append(AnalyticalBundle(
                operator="compare_contrast",
                atom_ids=atom_ids,
                output={
                    "agreements": agreements,
                    "differences": differences,
                },
                metadata={"entity": entity, "group_size": len(group)},
            ))

        return bundles

    except Exception as e:
        logger.debug(f"[analytical_operators] compare_contrast_bundle failed: {e}")
        return []


# ──────────────────────────────────────────────────────────────
# 2. tradeoff_extraction
# ──────────────────────────────────────────────────────────────

def tradeoff_extraction(atoms: List[RetrievedItem]) -> Optional[AnalyticalBundle]:
    """
    Classify each atom as 'pro', 'con', or 'neutral' based on language patterns.
    Returns an AnalyticalBundle with pros and cons lists.
    Returns None if no atoms are classified as either pro or con.
    """
    try:
        sorted_atoms = _sort_atoms(atoms)
        pros = []
        cons = []

        for atom in sorted_atoms:
            text = atom.content
            is_pro = bool(_PRO_PATTERNS.search(text))
            is_con = bool(_CON_PATTERNS.search(text))

            if is_pro and not is_con:
                pros.append({"atom_id": atom.citation_key, "content": text})
            elif is_con and not is_pro:
                cons.append({"atom_id": atom.citation_key, "content": text})
            elif is_pro and is_con:
                # Mixed: assign to whichever has more matches
                pro_count = len(_PRO_PATTERNS.findall(text))
                con_count = len(_CON_PATTERNS.findall(text))
                if pro_count >= con_count:
                    pros.append({"atom_id": atom.citation_key, "content": text})
                else:
                    cons.append({"atom_id": atom.citation_key, "content": text})

        if not pros and not cons:
            return None

        all_ids = [a.citation_key for a in sorted_atoms if
                   any(entry["atom_id"] == a.citation_key for entry in pros + cons)]

        return AnalyticalBundle(
            operator="tradeoff",
            atom_ids=all_ids,
            output={"pros": pros, "cons": cons},
            metadata={"pro_count": len(pros), "con_count": len(cons)},
        )

    except Exception as e:
        logger.debug(f"[analytical_operators] tradeoff_extraction failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 3. method_result_pairing
# ──────────────────────────────────────────────────────────────

_METHOD_TYPES = {"methodology", "method", "procedure"}
_RESULT_TYPES = {"result", "outcome", "finding", "conclusion"}


def method_result_pairing(atoms: List[RetrievedItem]) -> Optional[AnalyticalBundle]:
    """
    Pair atoms with item_type in METHOD_TYPES with atoms in RESULT_TYPES.
    Each methodology atom is paired with its nearest result atom by list order.
    Returns None if no method or no result atoms exist.
    """
    try:
        sorted_atoms = _sort_atoms(atoms)
        methods = [a for a in sorted_atoms if a.item_type.lower() in _METHOD_TYPES]
        results = [a for a in sorted_atoms if a.item_type.lower() in _RESULT_TYPES]

        if not methods or not results:
            return None

        pairs = []
        for i, method in enumerate(methods):
            result = results[i % len(results)]
            pairs.append({
                "method_atom_id": method.citation_key,
                "result_atom_id": result.citation_key,
                "method": method.content,
                "result": result.content,
            })

        all_ids = [a.citation_key for a in methods + results]

        return AnalyticalBundle(
            operator="method_result",
            atom_ids=sorted(set(all_ids)),
            output={"pairs": pairs},
            metadata={"method_count": len(methods), "result_count": len(results)},
        )

    except Exception as e:
        logger.debug(f"[analytical_operators] method_result_pairing failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 4. consensus_divergence
# ──────────────────────────────────────────────────────────────

_CONSENSUS_OVERLAP_THRESHOLD = 0.25  # Jaccard similarity for "agreement"


def consensus_divergence(atoms: List[RetrievedItem]) -> Optional[AnalyticalBundle]:
    """
    For ≥3 atoms: compute pairwise Jaccard similarity.
    Consensus: atoms that share ≥THRESHOLD overlap with majority of others.
    Divergent: atoms with no significant overlap with any other atom.

    Returns None if fewer than 3 atoms.
    """
    try:
        if len(atoms) < 3:
            return None

        sorted_atoms = _sort_atoms(atoms)
        token_sets = [_token_set(a.content) for a in sorted_atoms]
        n = len(sorted_atoms)

        # For each atom, count how many others it has >= threshold overlap with
        overlap_counts = [0] * n
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                union = token_sets[i] | token_sets[j]
                if not union:
                    continue
                jaccard = len(token_sets[i] & token_sets[j]) / len(union)
                if jaccard >= _CONSENSUS_OVERLAP_THRESHOLD:
                    overlap_counts[i] += 1

        majority_threshold = (n - 1) / 2  # more than half the other atoms

        consensus = []
        divergent = []
        for i, atom in enumerate(sorted_atoms):
            if overlap_counts[i] >= majority_threshold:
                consensus.append(atom.content)
            elif overlap_counts[i] == 0:
                divergent.append({
                    "atom_id": atom.citation_key,
                    "content": atom.content,
                })

        atom_ids = [a.citation_key for a in sorted_atoms]

        return AnalyticalBundle(
            operator="consensus_divergence",
            atom_ids=atom_ids,
            output={
                "consensus": consensus,
                "divergent": divergent,
                "total": n,
            },
            metadata={"threshold": _CONSENSUS_OVERLAP_THRESHOLD},
        )

    except Exception as e:
        logger.debug(f"[analytical_operators] consensus_divergence failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 5. source_authority_weight
# ──────────────────────────────────────────────────────────────

_LEVEL_FACTORS = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4}
_RECENCY_DECAY_DAYS = 3650  # 10-year full decay window


def source_authority_weight(atoms: List[RetrievedItem]) -> Optional[AnalyticalBundle]:
    """
    Score each atom: trust_score × level_factor × recency_factor.
    - level_factor: A=1.0, B=0.8, C=0.6, D=0.4 (default 0.5 for unknown)
    - recency_factor: max(0.1, 1.0 - recency_days / DECAY_DAYS)

    Returns bundle with scores dict and ranked list (desc). Ties broken by citation_key asc.
    Returns None if no atoms.
    """
    try:
        if not atoms:
            return None

        sorted_atoms = _sort_atoms(atoms)
        scores: Dict[str, float] = {}

        for atom in sorted_atoms:
            level = atom.knowledge_level.upper() if atom.knowledge_level else "B"
            level_factor = _LEVEL_FACTORS.get(level, 0.5)
            recency_factor = max(0.1, 1.0 - atom.recency_days / _RECENCY_DECAY_DAYS)
            score = atom.trust_score * level_factor * recency_factor
            scores[atom.citation_key] = round(score, 6)

        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))

        return AnalyticalBundle(
            operator="source_authority",
            atom_ids=[a.citation_key for a in sorted_atoms],
            output={
                "scores": scores,
                "ranked": ranked,
            },
            metadata={"decay_window_days": _RECENCY_DECAY_DAYS},
        )

    except Exception as e:
        logger.debug(f"[analytical_operators] source_authority_weight failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 6. change_detection
# ──────────────────────────────────────────────────────────────

def change_detection(atoms: List[RetrievedItem]) -> Optional[AnalyticalBundle]:
    """
    Detect metric change between the oldest and newest atom with numeric values.
    Oldest = highest recency_days, newest = lowest recency_days.
    Returns None if fewer than 2 atoms have numeric values or both share same recency_days.

    Output: {from, to, delta, pct_change}
    """
    try:
        sorted_atoms = _sort_atoms(atoms)

        # Find atoms with numeric values
        numeric_atoms: List[Tuple[RetrievedItem, float]] = []
        for atom in sorted_atoms:
            val = _extract_first_number(atom.content)
            if val is not None:
                numeric_atoms.append((atom, val))

        if len(numeric_atoms) < 2:
            return None

        # Sort by recency_days descending (highest = oldest)
        numeric_atoms.sort(key=lambda x: (-x[0].recency_days, x[0].citation_key or ''))

        oldest_atom, old_val = numeric_atoms[0]
        newest_atom, new_val = numeric_atoms[-1]

        # Skip if same recency (can't determine direction)
        if oldest_atom.recency_days == newest_atom.recency_days:
            return None

        delta = new_val - old_val
        pct_change = ((new_val - old_val) / old_val) * 100.0 if old_val != 0 else 0.0

        return AnalyticalBundle(
            operator="change_detection",
            atom_ids=[oldest_atom.citation_key, newest_atom.citation_key],
            output={
                "from": {
                    "atom_id": oldest_atom.citation_key,
                    "value": old_val,
                    "recency_days": oldest_atom.recency_days,
                },
                "to": {
                    "atom_id": newest_atom.citation_key,
                    "value": new_val,
                    "recency_days": newest_atom.recency_days,
                },
                "delta": delta,
                "pct_change": pct_change,
            },
            metadata={"formula": "((new - old) / old) * 100"},
        )

    except Exception as e:
        logger.debug(f"[analytical_operators] change_detection failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────

def run_all_operators(atoms: List[RetrievedItem]) -> List[AnalyticalBundle]:
    """
    Run all analytical operators on the provided atoms.
    Collects all non-None results into a flat list.
    Failures in any operator are silently skipped.
    """
    results: List[AnalyticalBundle] = []

    try:
        bundles = compare_contrast_bundle(atoms)
        results.extend(bundles)
    except Exception as e:
        logger.debug(f"[run_all_operators] compare_contrast_bundle failed: {e}")

    for op_fn in (
        tradeoff_extraction,
        method_result_pairing,
        consensus_divergence,
        source_authority_weight,
        change_detection,
    ):
        try:
            bundle = op_fn(atoms)
            if bundle is not None:
                results.append(bundle)
        except Exception as e:
            logger.debug(f"[run_all_operators] {op_fn.__name__} failed: {e}")

    return results
