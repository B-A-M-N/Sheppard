"""
cmk/evidence_pack.py — Assembles scored atoms into confidence-tiered blocks.

Builds structured evidence packs with:
  - HIGH_CONFIDENCE: reliability >= 0.75 (used as truth)
  - SUPPORTING_CONTEXT: 0.5 <= reliability < 0.75 (used for explanation)
  - LOW_CONFIDENCE: reliability < 0.5 (ignored unless reasoning about uncertainty)
  - CONTRADICTIONS: detected conflicting evidence
  - EXCLUDED: atoms filtered by evidence plan

With grounding enforcement:
  - Anti-paraphrase deduplication before assembly
  - Speculative atom exclusion
  - Abstraction gate metadata
  - Novelty analysis
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from .types import CMKAtom
from .evidence_planner import EvidencePlan
from .contradiction_detector import ContradictionDetector
from .grounding import (
    deduplicate_by_similarity,
    check_abstraction_eligibility,
    check_definition_support,
    analyze_novelty,
    DedupedAtom,
    AbstractionGate,
)


@dataclass
class EvidencePack:
    """
    Structured evidence ready for LLM injection.
    """
    high_confidence: List[CMKAtom] = field(default_factory=list)
    supporting_context: List[CMKAtom] = field(default_factory=list)
    low_confidence: List[CMKAtom] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    excluded: List[CMKAtom] = field(default_factory=list)

    # Grounding metadata
    abstraction_gate: Optional[AbstractionGate] = None
    definition_supported: bool = False
    novelty_analysis: Dict[str, Any] = field(default_factory=dict)
    dedup_count: int = 0

    # Metadata
    total_atoms: int = 0
    plan_applied: Optional[EvidencePlan] = None

    @property
    def is_empty(self) -> bool:
        return (
            len(self.high_confidence) == 0
            and len(self.supporting_context) == 0
            and len(self.low_confidence) == 0
        )

    @property
    def usable_atoms(self) -> List[CMKAtom]:
        """Atoms available for primary reasoning."""
        return self.high_confidence + self.supporting_context

    @property
    def grounded_atoms(self) -> List[CMKAtom]:
        """Only observed/inferred atoms (excludes speculative)."""
        return [a for a in self.usable_atoms if a.atom_state != "speculative"]

    def to_prompt_context(self) -> str:
        """
        Format the evidence pack as an LLM-injectable context block.
        """
        if self.is_empty:
            return "No relevant knowledge found for this query."

        sections = []

        # High confidence section
        if self.high_confidence:
            sections.append("HIGH CONFIDENCE FACTS (use as truth):")
            for i, atom in enumerate(self.high_confidence, 1):
                atom_id = f"[{atom.id}]" if atom.id else ""
                sections.append(f"  [{i}] {atom.content} {atom_id}")

        # Supporting context section
        if self.supporting_context:
            sections.append("\nSUPPORTING CONTEXT (use for explanation only):")
            for i, atom in enumerate(self.supporting_context, 1):
                atom_id = f"[{atom.id}]" if atom.id else ""
                sections.append(f"  [{i}] {atom.content} {atom_id}")

        # Contradictions section
        if self.contradictions:
            sections.append("\nCONFLICTING EVIDENCE (acknowledge if relevant):")
            for i, contradiction in enumerate(self.contradictions, 1):
                sections.append(
                    f"  [{i}] Conflict: {contradiction.get('description', 'Unknown')}"
                )
                if 'atom_a' in contradiction and 'atom_b' in contradiction:
                    sections.append(
                        f"      vs: {contradiction['atom_a']} "
                        f"/ {contradiction['atom_b']}"
                    )

        # Low confidence section (only if high/supporting are empty)
        if not self.high_confidence and not self.supporting_context and self.low_confidence:
            sections.append("\nLOW CONFIDENCE (use with caution — may be unreliable):")
            for i, atom in enumerate(self.low_confidence[:10], 1):
                sections.append(f"  [{i}] {atom.content}")

        # Add abstraction gate warning if applicable
        if self.abstraction_gate and not self.abstraction_gate.can_generalize:
            sections.append(
                f"\n⚠ ABSTRACTION BLOCKED: {self.abstraction_gate.reason}"
            )

        return "\n".join(sections)


class EvidencePackBuilder:
    """
    Assembles scored, sorted atoms into an EvidencePack.

    With grounding enforcement:
      1. Filter speculative atoms
      2. Deduplicate semantic duplicates
      3. Check abstraction gate
      4. Check definition support
      5. Analyze novelty
      6. Assemble into tiers
    """

    # Confidence thresholds
    HIGH_THRESHOLD = 0.75
    MEDIUM_THRESHOLD = 0.5

    # 8B model context throttling
    MAX_ATOMS = 12
    MAX_HIGH = 6
    MAX_SUPPORTING = 6

    def __init__(self):
        self.contradiction_detector = ContradictionDetector()

    def build(
        self,
        scored_atoms: List[tuple[CMKAtom, float]],
        plan: Optional[EvidencePlan] = None,
        concepts: Optional[List] = None,
    ) -> EvidencePack:
        """
        Build an EvidencePack from scored atoms with grounding enforcement.

        Args:
            scored_atoms: List of (atom, score) tuples (should be pre-sorted)
            plan: Optional evidence plan for filtering
            concepts: Optional concept list for abstraction gate

        Returns:
            EvidencePack with tiered knowledge and grounding metadata
        """
        if not scored_atoms:
            return EvidencePack(total_atoms=0, plan_applied=plan)

        # Step 1: Filter speculative atoms (they can't support generalization)
        grounded = [(a, s) for a, s in scored_atoms if a.atom_state != "speculative"]

        # Step 2: Deduplicate semantic duplicates
        atoms_only = [a for a, _ in grounded]
        dedup_results = deduplicate_by_similarity(atoms_only)

        # Build lookup of which atoms survived dedup
        survived_ids = {dr.atom.id for dr in dedup_results if not dr.is_duplicate}
        dedup_count = sum(1 for dr in dedup_results if dr.is_duplicate)

        grounded = [(a, s) for a, s in grounded if a.id in survived_ids]

        # Step 3: Apply plan-based filtering
        filtered = []
        for atom, score in grounded:
            # Check if excluded by plan
            if plan and atom.atom_type in plan.exclude:
                continue

            # Check minimum reliability threshold from plan
            if plan and atom.reliability < plan.min_reliability:
                continue

            filtered.append((atom, score))

        # Step 4: 8B context throttling — cap total atoms
        # Prioritize HIGH confidence atoms
        high_candidates = [(a, s) for a, s in filtered if a.reliability >= self.HIGH_THRESHOLD]
        supporting_candidates = [(a, s) for a, s in filtered if self.MEDIUM_THRESHOLD <= a.reliability < self.HIGH_THRESHOLD]
        low_candidates = [(a, s) for a, s in filtered if a.reliability < self.MEDIUM_THRESHOLD]

        high_confidence = [a for a, _ in high_candidates[:self.MAX_HIGH]]
        supporting_context = [a for a, _ in supporting_candidates[:self.MAX_SUPPORTING]]

        # If we have room, fill from low confidence
        remaining = self.MAX_ATOMS - len(high_confidence) - len(supporting_context)
        low_used = []
        if remaining > 0:
            low_used = [a for a, _ in low_candidates[:remaining]]

        # Step 5: Detect contradictions
        usable = high_confidence + supporting_context
        contradictions = self.contradiction_detector.detect(usable)

        # Build set of contradictory atom IDs
        contradictory_ids = set()
        for c in contradictions:
            contradictory_ids.add(c.get("atom_a", ""))
            contradictory_ids.add(c.get("atom_b", ""))

        # Step 6: Check abstraction gate
        abstraction_gate = check_abstraction_eligibility(usable, concepts)

        # Step 7: Check definition support
        def_supported, _ = check_definition_support(usable)

        # Step 8: Analyze novelty
        novelty = analyze_novelty(usable)

        return EvidencePack(
            high_confidence=high_confidence,
            supporting_context=supporting_context,
            low_confidence=low_used,
            contradictions=contradictions,
            excluded=[a for a, _ in scored_atoms if a not in usable and a not in low_used],
            total_atoms=len(scored_atoms),
            plan_applied=plan,
            abstraction_gate=abstraction_gate,
            definition_supported=def_supported,
            novelty_analysis=novelty,
            dedup_count=dedup_count,
        )
