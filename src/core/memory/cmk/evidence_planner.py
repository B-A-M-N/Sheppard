"""
cmk/evidence_planner.py — Generates retrieval instructions from intent.

Maps IntentProfile → EvidencePlan with:
  - must_have: required atom types/content patterns
  - should_have: helpful but optional atoms
  - optional: nice-to-have context
  - exclude: atom types to filter out
  - target_count: how many atoms to aim for
  - min_reliability: minimum reliability threshold
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .intent_profiler import IntentProfile


@dataclass
class EvidencePlan:
    must_have: List[str] = field(default_factory=list)
    should_have: List[str] = field(default_factory=list)
    optional: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    target_count: int = 20
    min_reliability: float = 0.3
    boost_types: List[str] = field(default_factory=list)  # atom types to boost in scoring


class EvidencePlanner:
    """
    Generates retrieval instructions from intent profile.

    Different query types need different evidence strategies.
    """

    def plan(self, intent: IntentProfile) -> EvidencePlan:
        """
        Build an EvidencePlan from an IntentProfile.

        Args:
            intent: The classified query intent

        Returns:
            EvidencePlan with retrieval directives
        """
        if intent.type == "factual":
            return self._plan_factual(intent)
        elif intent.type == "comparative":
            return self._plan_comparative(intent)
        elif intent.type == "procedural":
            return self._plan_procedural(intent)
        elif intent.type == "conceptual":
            return self._plan_conceptual(intent)
        else:
            return self._plan_exploratory(intent)

    def _plan_factual(self, intent: IntentProfile) -> EvidencePlan:
        """Factual queries: definitions, core facts only."""
        plan = EvidencePlan(
            must_have=["definition", "fact"],
            should_have=["supporting fact"],
            exclude=["opinion", "example"],
            target_count=10,
            min_reliability=0.6,
            boost_types=["definition", "fact"],
        )

        if intent.depth == "deep":
            plan.should_have.extend(["mechanism", "example"])
            plan.target_count = 20

        if intent.stability == "evolving":
            plan.min_reliability = 0.5  # Allow newer, less-verified info

        return plan

    def _plan_comparative(self, intent: IntentProfile) -> EvidencePlan:
        """Comparative queries: need facts about both sides + differences."""
        plan = EvidencePlan(
            must_have=["definition", "fact", "comparison"],
            should_have=["tradeoff", "advantage", "disadvantage"],
            optional=["example"],
            exclude=["opinion"],
            target_count=25,
            min_reliability=0.5,
            boost_types=["comparison", "tradeoff"],
        )

        if intent.depth == "deep":
            plan.should_have.extend(["mechanism", "failure_mode"])
            plan.target_count = 35

        return plan

    def _plan_procedural(self, intent: IntentProfile) -> EvidencePlan:
        """Procedural queries: steps, mechanisms, constraints."""
        plan = EvidencePlan(
            must_have=["procedure", "mechanism"],
            should_have=["constraint", "tradeoff", "failure_mode"],
            optional=["example", "metric"],
            exclude=["opinion"],
            target_count=20,
            min_reliability=0.5,
            boost_types=["procedure", "mechanism"],
        )

        if intent.depth == "deep":
            plan.should_have.extend(["edge case", "alternative"])
            plan.target_count = 30

        return plan

    def _plan_conceptual(self, intent: IntentProfile) -> EvidencePlan:
        """Conceptual queries: mechanisms, causal structure, deep explanations."""
        plan = EvidencePlan(
            must_have=["definition", "mechanism"],
            should_have=["causal fact", "constraint", "example"],
            optional=["metric", "tradeoff"],
            exclude=[],
            target_count=25,
            min_reliability=0.4,
            boost_types=["mechanism", "causal fact"],
        )

        if intent.depth == "deep":
            plan.should_have.extend(["edge case", "counterpoint"])
            plan.target_count = 35
            plan.min_reliability = 0.35

        return plan

    def _plan_exploratory(self, intent: IntentProfile) -> EvidencePlan:
        """Exploratory queries: broad, open-ended."""
        plan = EvidencePlan(
            must_have=["definition"],
            should_have=["fact", "mechanism"],
            optional=["example", "tradeoff", "metric"],
            exclude=[],
            target_count=30,
            min_reliability=0.3,
            boost_types=[],
        )

        return plan
