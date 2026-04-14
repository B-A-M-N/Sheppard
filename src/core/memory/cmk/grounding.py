"""
cmk/grounding.py — Anti-hallucination runtime constraints.

Enforces:
  1. Evidence-locked context — every claim must cite specific atom IDs
  2. Anti-paraphrase deduplication — remove semantically redundant atoms
  3. Abstraction gating — block generalization unless ≥2 clusters support it
  4. Multi-source support rule — definitions require ≥2 distinct atoms
  5. Novelty filter — each fact must introduce distinct information

This is where the CMK stops being a "retrieval system feeding a generator"
and becomes a "fact constraint system controlling a generator".
"""

import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field

from .types import CMKAtom, Concept

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 1. Anti-paraphrase deduplication
# ──────────────────────────────────────────────────────────────

@dataclass
class DedupedAtom:
    """Atom with deduplication metadata."""
    atom: CMKAtom
    is_duplicate: bool
    duplicate_of: Optional[str]  # atom_id of the canonical version
    similarity_to_canonical: float = 0.0


def deduplicate_by_similarity(
    atoms: List[CMKAtom],
    similarity_threshold: float = 0.92,
) -> List[DedupedAtom]:
    """
    Remove semantically redundant atoms (paraphrased duplicates).

    Two atoms are duplicates if their embeddings are highly similar.
    Keeps the highest-reliability atom as the canonical version.

    Args:
        atoms: List of atoms to deduplicate
        similarity_threshold: Cosine similarity above which atoms are considered duplicates

    Returns:
        List of DedupedAtom with duplicate flags
    """
    if len(atoms) < 2:
        return [DedupedAtom(atom=a, is_duplicate=False, duplicate_of=None) for a in atoms]

    # Filter to atoms with embeddings
    atoms_with_embeddings = [a for a in atoms if a.embedding is not None]

    if not atoms_with_embeddings:
        return [DedupedAtom(atom=a, is_duplicate=False, duplicate_of=None) for a in atoms]

    import numpy as np

    # Sort by reliability descending (keep best first)
    atoms_with_embeddings.sort(key=lambda x: x.reliability, reverse=True)

    canonical_atoms: List[CMKAtom] = []
    duplicate_map: Dict[str, tuple[str, float]] = {}  # atom_id → (canonical_id, similarity)

    for atom in atoms_with_embeddings:
        # Compare against all canonical atoms
        is_dup = False
        for canon in canonical_atoms:
            sim = _cosine(atom.embedding, canon.embedding)
            if sim >= similarity_threshold:
                duplicate_map[atom.id] = (canon.id, sim)
                is_dup = True
                break

        if not is_dup:
            canonical_atoms.append(atom)

    # Build results
    results = []
    for atom in atoms:
        if atom.id in duplicate_map:
            canon_id, sim = duplicate_map[atom.id]
            results.append(DedupedAtom(
                atom=atom,
                is_duplicate=True,
                duplicate_of=canon_id,
                similarity_to_canonical=sim,
            ))
        else:
            results.append(DedupedAtom(
                atom=atom,
                is_duplicate=False,
                duplicate_of=None,
            ))

    dup_count = sum(1 for r in results if r.is_duplicate)
    if dup_count > 0:
        logger.info(f"[dedup] Removed {dup_count} duplicate atoms from {len(atoms)}")

    return results


def _cosine(a: List[float], b: List[float]) -> float:
    import numpy as np
    a_np = np.array(a, dtype=float)
    b_np = np.array(b, dtype=float)
    norm_a = np.linalg.norm(a_np)
    norm_b = np.linalg.norm(b_np)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_np, b_np) / (norm_a * norm_b))


# ──────────────────────────────────────────────────────────────
# 2. Abstraction gating
# ──────────────────────────────────────────────────────────────

@dataclass
class AbstractionGate:
    """Result of abstraction eligibility check."""
    can_generalize: bool
    reason: str
    cluster_count: int = 0
    distinct_sources: int = 0
    atom_count: int = 0


def check_abstraction_eligibility(
    atoms: List[CMKAtom],
    concepts: Optional[List[Concept]] = None,
    min_clusters: int = 2,
    min_atoms: int = 3,
) -> AbstractionGate:
    """
    Check whether the evidence supports generalization/abstraction.

    Abstraction is only allowed if:
      - At least min_atoms distinct atoms are available
      - Those atoms span at least min_clusters different semantic clusters
        (OR come from at least 2 distinct sources)

    This prevents the LLM from generalizing from a single data point.

    Args:
        atoms: Available evidence atoms
        concepts: Optional concept assignments (for cluster counting)
        min_clusters: Minimum clusters required for abstraction
        min_atoms: Minimum atoms required for abstraction

    Returns:
        AbstractionGate with eligibility decision
    """
    atom_count = len(atoms)

    if atom_count < min_atoms:
        return AbstractionGate(
            can_generalize=False,
            reason=f"insufficient_atoms: have {atom_count}, need {min_atoms}",
            atom_count=atom_count,
        )

    # Count distinct clusters
    cluster_count = 1  # Default: assume single cluster if no concept info
    if concepts:
        # Count how many different concepts these atoms belong to
        atom_ids = {a.id for a in atoms}
        assigned_concepts = set()
        for concept in concepts:
            if any(aid in concept.atom_ids for aid in atom_ids):
                assigned_concepts.add(concept.id)
        cluster_count = max(1, len(assigned_concepts))

    # Count distinct sources
    sources = {a.source_id for a in atoms if a.source_id}
    distinct_sources = max(1, len(sources))

    # Gate logic
    if cluster_count >= min_clusters:
        return AbstractionGate(
            can_generalize=True,
            reason=f"sufficient_clusters: {cluster_count} clusters, {distinct_sources} sources",
            cluster_count=cluster_count,
            distinct_sources=distinct_sources,
            atom_count=atom_count,
        )

    if distinct_sources >= 2:
        return AbstractionGate(
            can_generalize=True,
            reason=f"multiple_sources: {distinct_sources} sources span {cluster_count} clusters",
            cluster_count=cluster_count,
            distinct_sources=distinct_sources,
            atom_count=atom_count,
        )

    return AbstractionGate(
        can_generalize=False,
        reason=f"single_source_cluster: {cluster_count} cluster, {distinct_sources} source(s) — no abstraction allowed",
        cluster_count=cluster_count,
        distinct_sources=distinct_sources,
        atom_count=atom_count,
    )


# ──────────────────────────────────────────────────────────────
# 3. Multi-source support rule
# ──────────────────────────────────────────────────────────────

def check_definition_support(
    atoms: List[CMKAtom],
    min_atoms_for_definition: int = 2,
) -> tuple[bool, str]:
    """
    Check whether a definition/generalization is supported by evidence.

    A definition is only valid if:
      - At least min_atoms_for_definition distinct atoms cover the concept
      - At least one atom is a 'definition' or 'fact' type

    Args:
        atoms: Available evidence
        min_atoms_for_definition: Minimum atoms required to support a definition

    Returns:
        (is_supported, reason)
    """
    if len(atoms) < min_atoms_for_definition:
        return False, f"need_{min_atoms_for_definition}_atoms_for_definition_have_{len(atoms)}"

    # Check for at least one definition/fact type
    has_definition = any(a.atom_type in ("definition", "fact", "mechanism") for a in atoms)
    if not has_definition:
        return False, "no_definition_or_fact_atoms"

    return True, f"supported_by_{len(atoms)}_atoms"


# ──────────────────────────────────────────────────────────────
# 4. Evidence-locked context builder
# ──────────────────────────────────────────────────────────────

@dataclass
class EvidenceItem:
    """
    An evidence item with full grounding metadata.

    Every item the LLM sees must include:
      - raw text
      - atom ID (for citation)
      - confidence tier
      - similarity score (if available)
      - source info
    """
    text: str
    atom_id: str
    tier: str  # HIGH, MEDIUM, LOW
    atom_type: str
    reliability: float
    score: float = 0.0
    source_id: str = ""
    is_duplicate: bool = False
    duplicate_of: str = ""


def build_evidence_locked_context(
    atoms: List[CMKAtom],
    scores: Optional[List[float]] = None,
    tiers: Optional[List[str]] = None,
    dedup_results: Optional[List[DedupedAtom]] = None,
    abstraction_gate: Optional[AbstractionGate] = None,
    definition_supported: Optional[bool] = None,
) -> tuple[List[EvidenceItem], Dict[str, Any]]:
    """
    Build an evidence-locked context block.

    Every item is traceable to a specific atom.
    Includes gating metadata for the prompt to enforce constraints.

    Args:
        atoms: Evidence atoms (should be pre-filtered)
        scores: Optional relevance scores
        tiers: Optional tier assignments (HIGH/MEDIUM/LOW)
        dedup_results: Optional deduplication results
        abstraction_gate: Optional abstraction gate result

    Returns:
        (evidence_items, gating_metadata)
    """
    if scores is None:
        scores = [0.0] * len(atoms)
    if tiers is None:
        tiers = ["MEDIUM"] * len(atoms)

    # Build dedup lookup
    dedup_lookup: Dict[str, DedupedAtom] = {}
    if dedup_results:
        for dr in dedup_results:
            dedup_lookup[dr.atom.id] = dr

    # Build evidence items (skip duplicates)
    items: List[EvidenceItem] = []
    for atom, score, tier in zip(atoms, scores, tiers):
        # Skip duplicates
        dedup = dedup_lookup.get(atom.id)
        if dedup and dedup.is_duplicate:
            continue

        items.append(EvidenceItem(
            text=atom.content,
            atom_id=atom.id,
            tier=tier,
            atom_type=atom.atom_type,
            reliability=atom.reliability,
            score=score,
            source_id=atom.source_id,
        ))

    # Build gating metadata
    gating = {
        "can_generalize": abstraction_gate.can_generalize if abstraction_gate else True,
        "generalize_reason": abstraction_gate.reason if abstraction_gate else "not_checked",
        "definition_supported": definition_supported,
        "total_atoms_before_dedup": len(atoms),
        "total_atoms_after_dedup": len(items),
        "tiers": {
            "HIGH": sum(1 for i in items if i.tier == "HIGH"),
            "MEDIUM": sum(1 for i in items if i.tier == "MEDIUM"),
            "LOW": sum(1 for i in items if i.tier == "LOW"),
        },
    }

    return items, gating


# ──────────────────────────────────────────────────────────────
# 5. Novelty analysis (for prompt instruction)
# ──────────────────────────────────────────────────────────────

def analyze_novelty(atoms: List[CMKAtom]) -> Dict[str, Any]:
    """
    Analyze the novelty of the evidence set.

    Returns info about whether the evidence introduces distinct facts
    or is just rephrasing the same idea.

    Args:
        atoms: Evidence atoms

    Returns:
        Novelty analysis dict
    """
    if len(atoms) < 2:
        return {
            "novel": True,
            "distinct_facts": len(atoms),
            "rephrasing_risk": "low",
        }

    # Check content overlap via n-gram similarity
    def get_ngrams(text: str, n: int = 4) -> set:
        words = text.lower().split()
        return set(" ".join(words[i:i+n]) for i in range(len(words) - n + 1))

    overlapping_pairs = 0
    total_pairs = 0

    for i in range(len(atoms)):
        for j in range(i + 1, len(atoms)):
            total_pairs += 1
            ngrams_i = get_ngrams(atoms[i].content)
            ngrams_j = get_ngrams(atoms[j].content)

            if not ngrams_i or not ngrams_j:
                continue

            overlap = len(ngrams_i & ngrams_j) / min(len(ngrams_i), len(ngrams_j))
            if overlap > 0.5:
                overlapping_pairs += 1

    rephrase_ratio = overlapping_pairs / max(1, total_pairs)

    if rephrase_ratio > 0.5:
        risk = "high"
    elif rephrase_ratio > 0.25:
        risk = "medium"
    else:
        risk = "low"

    return {
        "novel": rephrase_ratio < 0.5,
        "distinct_facts": total_pairs - overlapping_pairs,
        "rephrasing_risk": risk,
        "rephrase_ratio": round(rephrase_ratio, 2),
    }
