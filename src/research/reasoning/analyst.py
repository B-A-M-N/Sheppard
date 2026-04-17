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


def _coerce_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ""
    return str(value)


def _coerce_list_of_dicts(value) -> List[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _coerce_list_of_strings(value) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


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

ANALYST_DRAFT_PROMPT_TEMPLATE = """PROBLEM FRAME:
{problem_summary}

STAGE 1: EVIDENCE MAP
- State what is known.
- State what conflicts.
- State what is missing.

STAGE 2: REASONING DRAFT
- Form a main diagnosis.
- Compare alternatives.
- Surface tradeoffs, tensions, assumptions, and residual uncertainty.
- Cite atom IDs inline for all factual claims.

EVIDENCE BRIEF:
{evidence_brief}

{contradiction_block}

Write a grounded freeform reasoning draft. Do not use JSON."""

ANALYST_PARSE_PROMPT_TEMPLATE = """Convert the following grounded reasoning draft into JSON.

DRAFT:
{draft}

Output JSON with exactly this schema:
{{
  "diagnosis": "diagnosis with citations",
  "confidence": 0.0,
  "reasoning": "main reasoning with citations",
  "alternatives": [{{"explanation": "...", "likelihood": "low|medium|high", "why_less_likely": "..."}}],
  "recommendation": "recommended action",
  "recommendation_rationale": "why",
  "risks": ["..."],
  "open_questions": ["..."],
  "key_atoms": ["[A1]"],
  "tensions": ["important evidence tensions or tradeoffs"],
  "unresolved_uncertainties": ["what remains unresolved"],
  "assumption_dependencies": ["assumptions the diagnosis depends on"],
  "best_counterargument": "strongest evidence-backed counterargument"
}}
Output only JSON."""

ANALYST_REFINE_PROMPT_TEMPLATE = """Revise the prior grounded draft using the critic feedback.

PROBLEM FRAME:
{problem_summary}

PRIOR ANALYSIS:
{prior_analysis}

CRITIC FEEDBACK:
- strongest objection: {strongest_objection}
- overclaims: {overclaims}
- overlooked atoms: {overlooked_atoms}
- hidden assumptions: {hidden_assumptions}
- required revisions: {required_revisions}

EVIDENCE BRIEF:
{evidence_brief}

Rules:
- Address each required revision directly.
- Do not discard supported conclusions unless the critic identifies a specific evidence failure.
- Keep all reasoning grounded in the evidence and cite atoms inline.
- Include a short section naming which revisions were applied.

Write a grounded freeform revision draft. Do not use JSON."""


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
    tensions: List[str] = field(default_factory=list)
    unresolved_uncertainties: List[str] = field(default_factory=list)
    assumption_dependencies: List[str] = field(default_factory=list)
    best_counterargument: str = ""
    revisions_applied: List[str] = field(default_factory=list)
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
                f"  CONFLICT [{c.get('type', 'direct')}]: {c.get('description', 'unnamed conflict')}\n"
                f"    CLAIM A: {c.get('claim_a', '')}\n"
                f"    CLAIM B: {c.get('claim_b', '')}\n"
                f"    WHY: {c.get('why', '')}\n"
                f"    RESOLUTION HINT: {c.get('resolution_hint', '')}"
            )
        return "\n".join(lines)

    async def analyze(self, packet: EvidencePacket, frame: ProblemFrame) -> AnalystOutput:
        """Run the Analyst over an EvidencePacket for a given ProblemFrame."""
        evidence_brief = self._format_evidence_brief(packet)
        contradiction_block = self._format_contradiction_block(packet)

        logger.info(
            "[Analyst] Analyzing problem '%s' with %d atoms",
            frame.raw_statement[:60],
            len(packet.atoms),
        )

        try:
            draft_prompt = ANALYST_DRAFT_PROMPT_TEMPLATE.format(
                problem_summary=frame.summary(),
                evidence_brief=evidence_brief,
                contradiction_block=contradiction_block,
            )
            draft = await self.ollama.complete(
                task=TaskType.ANALYSIS,
                prompt=draft_prompt,
                system_prompt=ANALYST_SYSTEM_PROMPT,
                max_tokens=2500,
            )
            parse_prompt = ANALYST_PARSE_PROMPT_TEMPLATE.format(draft=draft)
            raw = await self.ollama.complete(
                task=TaskType.ANALYSIS,
                prompt=parse_prompt,
                system_prompt=ANALYST_SYSTEM_PROMPT,
                max_tokens=2500,
            )
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                logger.warning("[Analyst] parse_failure stage=analyze reason=no_json")
                raise ValueError("No JSON in analyst response")
            data = json.loads(match.group(0))
            missing_fields = [
                field for field in ("diagnosis", "confidence", "reasoning", "recommendation")
                if field not in data
            ]
            if missing_fields:
                logger.warning("[Analyst] field_dropout stage=analyze missing=%s", ",".join(missing_fields))

            return AnalystOutput(
                diagnosis=_coerce_text(data.get("diagnosis", "Insufficient evidence for a diagnosis.")),
                confidence=float(data.get("confidence", 0.0)),
                reasoning=_coerce_text(data.get("reasoning", "")),
                alternatives=_coerce_list_of_dicts(data.get("alternatives", [])),
                recommendation=_coerce_text(data.get("recommendation", "")),
                recommendation_rationale=_coerce_text(data.get("recommendation_rationale", "")),
                risks=_coerce_list_of_strings(data.get("risks", [])),
                open_questions=_coerce_list_of_strings(data.get("open_questions", [])),
                key_atoms=_coerce_list_of_strings(data.get("key_atoms", [])),
                tensions=_coerce_list_of_strings(data.get("tensions", [])),
                unresolved_uncertainties=_coerce_list_of_strings(data.get("unresolved_uncertainties", [])),
                assumption_dependencies=_coerce_list_of_strings(data.get("assumption_dependencies", [])),
                best_counterargument=_coerce_text(data.get("best_counterargument", "")),
                raw_evidence_count=len(packet.atoms),
            )

        except Exception as exc:
            logger.error("[Analyst] Analysis failed: %s", exc)
            logger.warning("[Analyst] fallback_invoked stage=analyze")
            return AnalystOutput(
                diagnosis="Analysis could not be completed due to a processing error.",
                confidence=0.0,
                reasoning=f"Error: {exc}",
                recommendation="Review the evidence manually.",
                raw_evidence_count=len(packet.atoms),
            )

    async def refine(
        self,
        packet: EvidencePacket,
        frame: ProblemFrame,
        prior_output: AnalystOutput,
        critic_output,
    ) -> AnalystOutput:
        evidence_brief = self._format_evidence_brief(packet)
        prompt = ANALYST_REFINE_PROMPT_TEMPLATE.format(
            problem_summary=frame.summary(),
            prior_analysis=json.dumps({
                "diagnosis": getattr(prior_output, "diagnosis", ""),
                "reasoning": getattr(prior_output, "reasoning", ""),
                "recommendation": getattr(prior_output, "recommendation", ""),
                "confidence": getattr(prior_output, "confidence", 0.0),
            }, ensure_ascii=True),
            strongest_objection=critic_output.strongest_objection,
            overclaims=", ".join(getattr(critic_output, "overclaims", []) or []) or "none",
            overlooked_atoms=", ".join(getattr(critic_output, "overlooked_atoms", []) or []) or "none",
            hidden_assumptions=", ".join(getattr(critic_output, "hidden_assumptions", []) or []) or "none",
            required_revisions=", ".join(getattr(critic_output, "required_revisions", []) or []) or "none",
            evidence_brief=evidence_brief,
        )
        try:
            draft = await self.ollama.complete(
                task=TaskType.ANALYSIS,
                prompt=prompt,
                system_prompt=ANALYST_SYSTEM_PROMPT,
                max_tokens=2500,
            )
            parse_prompt = ANALYST_PARSE_PROMPT_TEMPLATE.format(draft=draft)
            raw = await self.ollama.complete(
                task=TaskType.ANALYSIS,
                prompt=parse_prompt,
                system_prompt=ANALYST_SYSTEM_PROMPT,
                max_tokens=2500,
            )
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                logger.warning("[Analyst] parse_failure stage=refine reason=no_json")
                raise ValueError("No JSON in analyst refinement response")
            data = json.loads(match.group(0))
            missing_fields = [
                field for field in ("diagnosis", "confidence", "reasoning", "recommendation")
                if field not in data
            ]
            if missing_fields:
                logger.warning("[Analyst] field_dropout stage=refine missing=%s", ",".join(missing_fields))
            return AnalystOutput(
                diagnosis=_coerce_text(data.get("diagnosis", getattr(prior_output, "diagnosis", ""))),
                confidence=float(data.get("confidence", getattr(prior_output, "confidence", 0.0))),
                reasoning=_coerce_text(data.get("reasoning", getattr(prior_output, "reasoning", ""))),
                alternatives=_coerce_list_of_dicts(data.get("alternatives", getattr(prior_output, "alternatives", []))),
                recommendation=_coerce_text(data.get("recommendation", getattr(prior_output, "recommendation", ""))),
                recommendation_rationale=_coerce_text(data.get("recommendation_rationale", getattr(prior_output, "recommendation_rationale", ""))),
                risks=_coerce_list_of_strings(data.get("risks", getattr(prior_output, "risks", []))),
                open_questions=_coerce_list_of_strings(data.get("open_questions", getattr(prior_output, "open_questions", []))),
                key_atoms=_coerce_list_of_strings(data.get("key_atoms", getattr(prior_output, "key_atoms", []))),
                tensions=_coerce_list_of_strings(data.get("tensions", getattr(prior_output, "tensions", []))),
                unresolved_uncertainties=_coerce_list_of_strings(data.get("unresolved_uncertainties", getattr(prior_output, "unresolved_uncertainties", []))),
                assumption_dependencies=_coerce_list_of_strings(data.get("assumption_dependencies", getattr(prior_output, "assumption_dependencies", []))),
                best_counterargument=_coerce_text(data.get("best_counterargument", getattr(prior_output, "best_counterargument", ""))),
                revisions_applied=_coerce_list_of_strings(getattr(critic_output, "required_revisions", [])),
                raw_evidence_count=len(packet.atoms),
            )
        except Exception as exc:
            logger.error("[Analyst] Refinement failed: %s", exc)
            logger.warning("[Analyst] fallback_invoked stage=refine")
            if hasattr(prior_output, "revisions_applied"):
                prior_output.revisions_applied = _coerce_list_of_strings(getattr(critic_output, "required_revisions", []))
                return prior_output
            return AnalystOutput(
                diagnosis=_coerce_text(getattr(prior_output, "diagnosis", "")),
                confidence=float(getattr(prior_output, "confidence", 0.0)),
                reasoning=_coerce_text(getattr(prior_output, "reasoning", "")),
                recommendation=_coerce_text(getattr(prior_output, "recommendation", "")),
                recommendation_rationale=_coerce_text(getattr(prior_output, "recommendation_rationale", "")),
                risks=_coerce_list_of_strings(getattr(prior_output, "risks", [])),
                open_questions=_coerce_list_of_strings(getattr(prior_output, "open_questions", [])),
                key_atoms=_coerce_list_of_strings(getattr(prior_output, "key_atoms", [])),
                revisions_applied=_coerce_list_of_strings(getattr(critic_output, "required_revisions", [])),
                raw_evidence_count=len(packet.atoms),
            )
