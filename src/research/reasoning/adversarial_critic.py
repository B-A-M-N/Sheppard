"""
reasoning/adversarial_critic.py

The Adversarial Critic — challenges the Analyst's output.

After the Analyst produces a diagnosis and recommendation, the Critic
runs a second pass over the same evidence to:
  1. Find the strongest argument AGAINST the Analyst's diagnosis
  2. Identify atoms the Analyst underweighted or ignored
  3. Check whether the Analyst handled contradictions correctly
  4. Produce a counter-recommendation if the evidence supports a different path

The Critic is not trying to be contrarian for its own sake. It is trying
to surface what the Analyst might have missed — the failure modes, the
edge cases, the evidence that points the other way.

The user sees both the Analyst's view and the Critic's challenge. They
can weigh them. That is more honest and more useful than a single
uncontested recommendation.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from src.llm.client import OllamaClient
from src.llm.model_router import TaskType
from src.research.reasoning.assembler import EvidencePacket
from src.research.reasoning.analyst import AnalystOutput

logger = logging.getLogger(__name__)


CRITIC_SYSTEM_PROMPT = """You are a rigorous adversarial critic tasked with stress-testing an Analyst's conclusion.
Your job is NOT to be contrarian. Your job is to find what the Analyst missed, underweighted, or got wrong.
You are working from the same evidence the Analyst used. Stay grounded — cite atoms.
Output ONLY valid JSON. No preamble, no markdown fences."""

CRITIC_PROMPT_TEMPLATE = """The Analyst has produced the following assessment of a problem.
Your job: challenge it. Find the holes. Surface what was missed.

ANALYST'S DIAGNOSIS:
{diagnosis}

ANALYST'S RECOMMENDATION:
{recommendation}

ANALYST'S REASONING:
{reasoning}

ANALYST'S CONFIDENCE: {confidence:.0%}

SAME EVIDENCE BRIEF (all atoms the Analyst had access to):
{evidence_brief}

{contradiction_block}

ATOMS THE ANALYST CITED AS KEY: {key_atoms}

Your task: produce the strongest possible challenge to the Analyst's position.

Output JSON with exactly this schema:
{{
  "strongest_objection": "The single most powerful argument against the Analyst's diagnosis or recommendation — with citations",
  "overclaims": ["claims the analyst made too broadly or without enough support"],
  "overlooked_atoms": ["Global IDs of atoms the Analyst underweighted or ignored that change the picture"],
  "overlooked_reasoning": "Why those atoms matter and what they imply",
  "hidden_assumptions": ["assumptions the analyst relied on but did not defend"],
  "required_revisions": ["concrete revision actions the analyst must apply"],
  "contradiction_verdict": "Did the Analyst handle the flagged contradictions correctly? If not, what was missed?",
  "counter_recommendation": "An alternative recommendation if the evidence supports a different path — null if the Analyst's recommendation is defensible",
  "counter_rationale": "Why the counter-recommendation is better supported — null if no counter",
  "confidence_assessment": "Is the Analyst's stated confidence appropriate? Too high, too low, or about right — and why",
  "synthesis": "One sentence: what does the user most need to know that the Analyst did not say?"
}}

Be specific. Vague objections are useless. If you cannot find a strong objection, say so clearly."""


@dataclass
class CriticOutput:
    strongest_objection: str
    overclaims: List[str] = field(default_factory=list)
    overlooked_atoms: List[str] = field(default_factory=list)
    overlooked_reasoning: str = ""
    hidden_assumptions: List[str] = field(default_factory=list)
    required_revisions: List[str] = field(default_factory=list)
    contradiction_verdict: str = ""
    counter_recommendation: Optional[str] = None
    counter_rationale: Optional[str] = None
    confidence_assessment: str = ""
    synthesis: str = ""


class AdversarialCritic:
    """
    Runs a second-pass adversarial review over the Analyst's output
    using the same EvidencePacket.
    """

    def __init__(self, ollama: OllamaClient):
        self.ollama = ollama

    def _format_evidence_brief(self, packet: EvidencePacket) -> str:
        lines = []
        for atom in packet.atoms:
            gid = atom.get("global_id", atom.get("citation_key", "[A?]"))
            atype = atom.get("type", atom.get("item_type", "claim"))
            text = atom.get("text", atom.get("content", ""))
            lines.append(f"{gid} [{atype}]\n  {text}")
        return "\n\n".join(lines) if lines else "(no evidence atoms)"

    def _format_contradiction_block(self, packet: EvidencePacket) -> str:
        if not packet.contradictions:
            return ""
        lines = ["FLAGGED CONTRADICTIONS:"]
        for c in packet.contradictions:
            lines.append(
                f"  [{c.get('type', 'direct')}] {c.get('description', '')}: "
                f"A='{c.get('claim_a', '')}' vs B='{c.get('claim_b', '')}'"
            )
        return "\n".join(lines)

    async def critique(self, analyst_output: AnalystOutput, packet: EvidencePacket) -> CriticOutput:
        """Challenge the Analyst's output using the same evidence."""
        evidence_brief = self._format_evidence_brief(packet)
        contradiction_block = self._format_contradiction_block(packet)

        prompt = CRITIC_PROMPT_TEMPLATE.format(
            diagnosis=analyst_output.diagnosis,
            recommendation=analyst_output.recommendation,
            reasoning=analyst_output.reasoning,
            confidence=analyst_output.confidence,
            evidence_brief=evidence_brief,
            contradiction_block=contradiction_block,
            key_atoms=", ".join(analyst_output.key_atoms) if analyst_output.key_atoms else "none specified",
        )

        logger.info("[Critic] Running adversarial review of Analyst output")

        try:
            raw = await self.ollama.complete(
                task=TaskType.CRITIQUE,
                prompt=prompt,
                system_prompt=CRITIC_SYSTEM_PROMPT,
                max_tokens=1500,
            )
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                logger.warning("[Critic] parse_failure reason=no_json")
                raise ValueError("No JSON in critic response")
            data = json.loads(match.group(0))

            return CriticOutput(
                strongest_objection=data.get("strongest_objection", "No significant objection found."),
                overclaims=data.get("overclaims", []),
                overlooked_atoms=data.get("overlooked_atoms", []),
                overlooked_reasoning=data.get("overlooked_reasoning", ""),
                hidden_assumptions=data.get("hidden_assumptions", []),
                required_revisions=data.get("required_revisions", []),
                contradiction_verdict=data.get("contradiction_verdict", ""),
                counter_recommendation=data.get("counter_recommendation"),
                counter_rationale=data.get("counter_rationale"),
                confidence_assessment=data.get("confidence_assessment", ""),
                synthesis=data.get("synthesis", ""),
            )

        except Exception as exc:
            logger.error("[Critic] Critique failed: %s", exc)
            logger.warning("[Critic] fallback_invoked")
            return CriticOutput(
                strongest_objection="Adversarial review could not be completed.",
                synthesis="Review the evidence and Analyst output manually.",
            )
