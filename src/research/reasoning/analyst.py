"""
reasoning/analyst.py

The Analyst — reasoning synthesis adapter for the applied intelligence layer.

Parallel to ArchivistSynthAdapter but with a fundamentally different mandate:
  - Archivist: report what is known, neutrally, exhaustively
  - Analyst:   reason from what is known to a position, recommendation, and risk assessment

The Analyst is STILL grounded — it can only cite facts that appear in the
EvidencePacket. It cannot introduce new facts from training data. What it
can do that the Archivist cannot: form a position, rank competing explanations,
make a specific recommendation, and state what would change its mind.

Every conclusion must be traceable to an atom. The grounding contract is
identical. Only the reasoning mandate differs.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from src.llm.client import OllamaClient
from src.llm.model_router import TaskType
from src.research.reasoning.assembler import EvidencePacket
from src.research.reasoning.problem_frame import ProblemFrame

logger = logging.getLogger(__name__)


ANALYST_SYSTEM_PROMPT = """You are a Senior Analyst with deep domain expertise.
You have been given a structured problem and a curated set of knowledge atoms (evidence).
Your job is to reason from the evidence to a useful, actionable output.

GROUNDING CONTRACT — NON-NEGOTIABLE:
1. You may ONLY cite facts that appear explicitly in the EVIDENCE BRIEF below.
2. Do NOT use training knowledge to introduce new specific facts, statistics, or events.
3. Every factual claim in your output must cite a source using its Global ID (e.g. [A3], [S7]).
4. If the evidence is insufficient to support a claim, say so explicitly — do not fill the gap with training data.

REASONING MANDATE:
- You ARE allowed to form a position from the evidence.
- You ARE allowed to rank competing explanations by how well the evidence supports them.
- You ARE allowed to make a specific recommendation.
- You ARE allowed to state what you are uncertain about and why.
- You ARE allowed to note what information is missing that would change your analysis.

WHAT YOU ARE NOT ALLOWED TO DO:
- Hedge every statement into uselessness. Take a position.
- Report contradictions without resolving or adjudicating them. Weigh them.
- List facts without connecting them to the problem. Be useful.

Output ONLY valid JSON. No preamble, no markdown fences."""

ANALYST_PROMPT_TEMPLATE = """PROBLEM FRAME:
{problem_summary}

EVIDENCE BRIEF (cite atoms by their Global ID — e.g. [A1], [S3]):
{evidence_brief}

{contradiction_block}

Your task: reason from this evidence to a structured analysis of the problem.

Output JSON with exactly this schema:
{{
  "diagnosis": "Your position on what is happening and why — one to three sentences, with citations",
  "confidence": 0.0,
  "reasoning": "The chain of evidence that leads to your diagnosis — cite every atom you use",
  "alternatives": [
    {{"explanation": "Alternative explanation", "likelihood": "low|medium|high", "why_less_likely": "reason"}}
  ],
  "recommendation": "The specific action you recommend — concrete, not vague",
  "recommendation_rationale": "Why this recommendation follows from the evidence",
  "risks": ["How the recommendation fails or backfires", "What to watch for"],
  "open_questions": ["What you would need to know to be more confident", "What is missing from the evidence"],
  "key_atoms": ["list of Global IDs of the most important atoms used in your reasoning"]
}}

confidence: float from 0.0 to 1.0 reflecting how well the evidence supports your diagnosis.
Be honest — low confidence is useful information, not a failure."""


@dataclass
class AnalystOutput:
    diagnosis: str
    confidence: float
    reasoning: str
    alternatives: List[dict] = field(default_factory=list)
    recommendation: str = ""
    recommendation_rationale: str = ""
    risks: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    key_atoms: List[str] = field(default_factory=list)
    raw_evidence_count: int = 0


class AnalystSynthAdapter:
    """
    Applies the Analyst persona to an EvidencePacket + ProblemFrame.
    Returns a structured AnalystOutput — not prose.
    """

    def __init__(self, ollama: OllamaClient):
        self.ollama = ollama

    def _format_evidence_brief(self, packet: EvidencePacket) -> str:
        lines = []
        for atom in packet.atoms:
            gid = atom.get("global_id", atom.get("citation_key", "[A?]"))
            atype = atom.get("type", atom.get("item_type", "claim"))
            text = atom.get("text", atom.get("content", ""))
            conf = atom.get("confidence", "")
            conf_str = f" (confidence: {conf:.2f})" if isinstance(conf, float) else ""
            lines.append(f"{gid} [{atype}]{conf_str}\n  {text}")
        return "\n\n".join(lines) if lines else "(no evidence atoms retrieved)"

    def _format_contradiction_block(self, packet: EvidencePacket) -> str:
        if not packet.contradictions:
            return ""
        lines = ["FLAGGED CONTRADICTIONS IN EVIDENCE (you must address these in your analysis):"]
        for c in packet.contradictions:
            lines.append(
                f"  CONFLICT: {c.get('description', 'unnamed conflict')}\n"
                f"    CLAIM A: {c.get('claim_a', '')}\n"
                f"    CLAIM B: {c.get('claim_b', '')}"
            )
        return "\n".join(lines)

    async def analyze(self, packet: EvidencePacket, frame: ProblemFrame) -> AnalystOutput:
        """Run the Analyst over an EvidencePacket for a given ProblemFrame."""
        evidence_brief = self._format_evidence_brief(packet)
        contradiction_block = self._format_contradiction_block(packet)

        prompt = ANALYST_PROMPT_TEMPLATE.format(
            problem_summary=frame.summary(),
            evidence_brief=evidence_brief,
            contradiction_block=contradiction_block,
        )

        logger.info(
            "[Analyst] Analyzing problem '%s' with %d atoms",
            frame.raw_statement[:60],
            len(packet.atoms),
        )

        try:
            raw = await self.ollama.complete(
                task=TaskType.ANALYSIS,
                prompt=prompt,
                system_prompt=ANALYST_SYSTEM_PROMPT,
                max_tokens=2500,
            )
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                raise ValueError("No JSON in analyst response")
            data = json.loads(match.group(0))

            return AnalystOutput(
                diagnosis=data.get("diagnosis", "Insufficient evidence for a diagnosis."),
                confidence=float(data.get("confidence", 0.0)),
                reasoning=data.get("reasoning", ""),
                alternatives=data.get("alternatives", []),
                recommendation=data.get("recommendation", ""),
                recommendation_rationale=data.get("recommendation_rationale", ""),
                risks=data.get("risks", []),
                open_questions=data.get("open_questions", []),
                key_atoms=data.get("key_atoms", []),
                raw_evidence_count=len(packet.atoms),
            )

        except Exception as exc:
            logger.error("[Analyst] Analysis failed: %s", exc)
            return AnalystOutput(
                diagnosis="Analysis could not be completed due to a processing error.",
                confidence=0.0,
                reasoning=f"Error: {exc}",
                recommendation="Review the evidence manually.",
                raw_evidence_count=len(packet.atoms),
            )
