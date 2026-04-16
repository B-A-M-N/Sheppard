"""
reasoning/problem_frame.py

Structured problem intake for the Analyst reasoning layer.

Takes a raw problem statement from the user and extracts a ProblemFrame:
the structured dimensions that drive targeted retrieval and focused reasoning.

The framer uses an LLM call (on the extraction host — lightweight) to parse
the problem into computable parts. If the LLM call fails, it falls back to
a simple heuristic frame so the pipeline never halts.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from src.llm.client import OllamaClient
from src.llm.model_router import TaskType

logger = logging.getLogger(__name__)

FRAMING_SYSTEM_PROMPT = """You are a problem analyst. Your job is to parse a raw problem statement
into structured components that will drive a knowledge retrieval and reasoning system.
Output ONLY valid JSON. No preamble, no markdown fences."""

FRAMING_PROMPT_TEMPLATE = """Parse this problem statement into structured components.

PROBLEM: {problem}

Output JSON with exactly this schema:
{{
  "symptoms": ["observable evidence of the problem — what is actually happening"],
  "goal": "the desired end state in one sentence",
  "constraints": ["hard limits: time, resources, scope, non-negotiables"],
  "domain_hints": ["knowledge domains most relevant to solving this — be specific"],
  "retrieval_queries": ["3 to 5 targeted search queries to find the most relevant knowledge atoms"],
  "problem_type": "one of: diagnostic | design | optimization | decision | explanation | prediction"
}}

Rules:
- symptoms: concrete, observable — what is broken or wrong right now
- goal: what success looks like, not a method
- domain_hints: specific (e.g. "TCP/IP networking" not "computers")
- retrieval_queries: targeted enough to pull specific atoms (not generic topic searches)
- if information is absent from the problem statement, use empty list or reasonable inference
"""


@dataclass
class ProblemFrame:
    raw_statement: str
    symptoms: List[str] = field(default_factory=list)
    goal: str = ""
    constraints: List[str] = field(default_factory=list)
    domain_hints: List[str] = field(default_factory=list)
    retrieval_queries: List[str] = field(default_factory=list)
    problem_type: str = "diagnostic"

    def primary_retrieval_query(self) -> str:
        """Best single query for a first-pass retrieval."""
        if self.retrieval_queries:
            return self.retrieval_queries[0]
        return self.raw_statement

    def all_retrieval_queries(self) -> List[str]:
        """All queries, falling back to raw statement if none were parsed."""
        return self.retrieval_queries if self.retrieval_queries else [self.raw_statement]

    def summary(self) -> str:
        lines = [f"Problem: {self.raw_statement}"]
        if self.goal:
            lines.append(f"Goal: {self.goal}")
        if self.symptoms:
            lines.append("Symptoms: " + "; ".join(self.symptoms))
        if self.constraints:
            lines.append("Constraints: " + "; ".join(self.constraints))
        if self.domain_hints:
            lines.append("Domains: " + ", ".join(self.domain_hints))
        return "\n".join(lines)


class ProblemFramer:
    """
    Uses an LLM call to parse a raw problem statement into a ProblemFrame.
    Falls back to a heuristic frame on any failure — never raises.
    """

    def __init__(self, ollama: OllamaClient):
        self.ollama = ollama

    async def frame(self, problem_statement: str) -> ProblemFrame:
        """Parse a problem statement into a structured ProblemFrame."""
        try:
            prompt = FRAMING_PROMPT_TEMPLATE.format(problem=problem_statement.strip())
            raw = await self.ollama.complete(
                task=TaskType.DECOMPOSITION,
                prompt=prompt,
                system_prompt=FRAMING_SYSTEM_PROMPT,
                max_tokens=800,
            )
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                raise ValueError("No JSON object in framing response")
            data = json.loads(match.group(0))

            return ProblemFrame(
                raw_statement=problem_statement,
                symptoms=data.get("symptoms", []),
                goal=data.get("goal", ""),
                constraints=data.get("constraints", []),
                domain_hints=data.get("domain_hints", []),
                retrieval_queries=data.get("retrieval_queries", [problem_statement]),
                problem_type=data.get("problem_type", "diagnostic"),
            )

        except Exception as exc:
            logger.warning("[ProblemFramer] LLM framing failed (%s), using heuristic frame", exc)
            return self._heuristic_frame(problem_statement)

    def _heuristic_frame(self, problem_statement: str) -> ProblemFrame:
        """Minimal frame derived without an LLM call."""
        words = problem_statement.lower().split()
        queries = [
            problem_statement,
            " ".join(words[:8]) if len(words) > 8 else problem_statement,
        ]
        return ProblemFrame(
            raw_statement=problem_statement,
            symptoms=[problem_statement],
            goal="Resolve the stated problem",
            constraints=[],
            domain_hints=[],
            retrieval_queries=queries,
            problem_type="diagnostic",
        )
