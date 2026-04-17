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
from enum import Enum
from typing import List, Optional

from src.llm.client import OllamaClient
from src.llm.model_router import TaskType

logger = logging.getLogger(__name__)

class RetrievalMode(str, Enum):
    TEMPORAL = "temporal"
    CANONICAL = "canonical"
    MIXED = "mixed"


FRAMING_SYSTEM_PROMPT = """You are a problem analyst. Your job is to parse a raw problem statement
into structured components that will drive a knowledge retrieval and reasoning system.
Output ONLY valid JSON. No preamble, no markdown fences."""

FRAMING_PROMPT_TEMPLATE = """Parse this problem statement into structured components.

PROBLEM: {problem}

Output JSON with exactly this schema:
{{
  "problem": "succinct restatement of the core problem",
  "symptoms": ["observable evidence of the problem — what is actually happening"],
  "goal": "the desired end state in one sentence",
  "constraints": ["hard limits: time, resources, scope, non-negotiables"],
  "dimensions": ["major reasoning dimensions such as mechanism, tradeoffs, constraints, failure_modes, implementation"],
  "unknowns": ["important missing information that would materially change the answer"],
  "domain_hints": ["knowledge domains most relevant to solving this — be specific"],
  "problem_type": "one of: diagnostic | design | optimization | decision | explanation | prediction",
  "retrieval_mode": "one of: temporal | canonical | mixed"
}}

Rules:
- symptoms: concrete, observable — what is broken or wrong right now
- goal: what success looks like, not a method
- dimensions: focus on mechanism, tradeoffs, constraints, failure modes, and implementation when relevant
- domain_hints: specific (e.g. "TCP/IP networking" not "computers")
- unknowns: only material uncertainties, not trivia
- if information is absent from the problem statement, use empty list or reasonable inference
"""

FRAMING_QUERY_PROMPT_TEMPLATE = """You already framed this problem.

PROBLEM: {problem}
FRAME:
{frame_json}

Generate targeted retrieval queries per dimension.

Output JSON with exactly this schema:
{{
  "retrieval_queries": ["queries covering the major dimensions"],
  "follow_up_queries": {{
    "dimension_name": ["1 to 3 deeper queries for that dimension"]
  }}
}}

Rules:
- Queries must be technical and specific, not generic topic searches
- Cover mechanism, tradeoffs, constraints, failure modes, and implementation when relevant
- Favor canonical/invariant phrasing for canonical questions
- Favor freshness/update phrasing only for temporal questions
"""


@dataclass
class ProblemFrame:
    raw_statement: str
    problem: str = ""
    symptoms: List[str] = field(default_factory=list)
    goal: str = ""
    constraints: List[str] = field(default_factory=list)
    dimensions: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    domain_hints: List[str] = field(default_factory=list)
    retrieval_queries: List[str] = field(default_factory=list)
    follow_up_queries: dict[str, List[str]] = field(default_factory=dict)
    problem_type: str = "diagnostic"
    retrieval_mode: str = RetrievalMode.MIXED.value

    def primary_retrieval_query(self) -> str:
        """Best single query for a first-pass retrieval."""
        if self.retrieval_queries:
            return self.retrieval_queries[0]
        return self.raw_statement

    def all_retrieval_queries(self) -> List[str]:
        """All queries, falling back to raw statement if none were parsed."""
        ordered = list(self.retrieval_queries) if self.retrieval_queries else [self.raw_statement]
        for dimension in self.dimensions:
            ordered.extend(self.follow_up_queries.get(dimension, []))
        seen = set()
        result = []
        for query in ordered:
            normalized = (query or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result or [self.raw_statement]

    def summary(self) -> str:
        lines = [f"Problem: {self.problem or self.raw_statement}"]
        if self.goal:
            lines.append(f"Goal: {self.goal}")
        if self.symptoms:
            lines.append("Symptoms: " + "; ".join(self.symptoms))
        if self.constraints:
            lines.append("Constraints: " + "; ".join(self.constraints))
        if self.dimensions:
            lines.append("Dimensions: " + "; ".join(self.dimensions))
        if self.unknowns:
            lines.append("Unknowns: " + "; ".join(self.unknowns))
        if self.domain_hints:
            lines.append("Domains: " + ", ".join(self.domain_hints))
        lines.append(f"Retrieval mode: {self.retrieval_mode}")
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

            base_frame = ProblemFrame(
                raw_statement=problem_statement,
                problem=str(data.get("problem", problem_statement)).strip(),
                symptoms=data.get("symptoms", []),
                goal=data.get("goal", ""),
                constraints=data.get("constraints", []),
                dimensions=data.get("dimensions", []) or self._default_dimensions(problem_statement),
                unknowns=data.get("unknowns", []),
                domain_hints=data.get("domain_hints", []),
                retrieval_queries=[],
                problem_type=data.get("problem_type", "diagnostic"),
                retrieval_mode=self._normalize_mode(
                    data.get("retrieval_mode") or self._classify_retrieval_mode(problem_statement)
                ),
            )

            query_prompt = FRAMING_QUERY_PROMPT_TEMPLATE.format(
                problem=problem_statement.strip(),
                frame_json=json.dumps({
                    "problem": base_frame.problem,
                    "dimensions": base_frame.dimensions,
                    "unknowns": base_frame.unknowns,
                    "domain_hints": base_frame.domain_hints,
                    "problem_type": base_frame.problem_type,
                    "retrieval_mode": base_frame.retrieval_mode,
                }, ensure_ascii=True),
            )
            query_raw = await self.ollama.complete(
                task=TaskType.DECOMPOSITION,
                prompt=query_prompt,
                system_prompt=FRAMING_SYSTEM_PROMPT,
                max_tokens=800,
            )
            query_match = re.search(r'\{.*\}', query_raw, re.DOTALL)
            if not query_match:
                raise ValueError("No JSON object in framing query response")
            query_data = json.loads(query_match.group(0))
            base_frame.retrieval_queries = query_data.get("retrieval_queries", []) or self._build_queries_from_dimensions(problem_statement, base_frame.dimensions)
            base_frame.follow_up_queries = {
                str(key): [str(item).strip() for item in value if str(item).strip()]
                for key, value in (query_data.get("follow_up_queries", {}) or {}).items()
                if isinstance(value, list)
            }
            return base_frame

        except Exception as exc:
            logger.warning("[ProblemFramer] LLM framing failed (%s), using heuristic frame", exc)
            return self._heuristic_frame(problem_statement)

    def _heuristic_frame(self, problem_statement: str) -> ProblemFrame:
        """Minimal frame derived without an LLM call."""
        dimensions = self._default_dimensions(problem_statement)
        queries = self._build_queries_from_dimensions(problem_statement, dimensions)
        return ProblemFrame(
            raw_statement=problem_statement,
            problem=problem_statement,
            symptoms=[problem_statement],
            goal="Resolve the stated problem",
            constraints=[],
            dimensions=dimensions,
            unknowns=[],
            domain_hints=[],
            retrieval_queries=queries,
            problem_type="diagnostic",
            retrieval_mode=self._classify_retrieval_mode(problem_statement),
        )

    def follow_up_for_dimensions(self, frame: ProblemFrame, weak_dimensions: List[str]) -> List[str]:
        queries: List[str] = []
        for dimension in weak_dimensions:
            if frame.follow_up_queries.get(dimension):
                queries.extend(frame.follow_up_queries[dimension][:3])
                continue
            queries.extend(self._build_queries_from_dimensions(frame.raw_statement, [dimension])[:3])
        deduped = []
        seen = set()
        for query in queries:
            if query and query not in seen:
                deduped.append(query)
                seen.add(query)
        return deduped

    @staticmethod
    def _default_dimensions(problem_statement: str) -> List[str]:
        return ["mechanism", "tradeoffs", "constraints", "failure_modes", "implementation"]

    def _build_queries_from_dimensions(self, problem_statement: str, dimensions: List[str]) -> List[str]:
        query_map = {
            "mechanism": f"{problem_statement} mechanism root cause how it works",
            "tradeoffs": f"{problem_statement} tradeoffs compare alternatives",
            "constraints": f"{problem_statement} constraints limits assumptions",
            "failure_modes": f"{problem_statement} failure modes risks edge cases",
            "implementation": f"{problem_statement} implementation operational details",
        }
        return [query_map.get(dimension, f"{problem_statement} {dimension}") for dimension in dimensions]

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        value = str(mode or "").strip().lower()
        if value in {item.value for item in RetrievalMode}:
            return value
        return RetrievalMode.MIXED.value

    @staticmethod
    def _classify_retrieval_mode(problem_statement: str) -> str:
        text = (problem_statement or "").lower()
        temporal_markers = {"latest", "recent", "current", "today", "update", "changed", "new"}
        canonical_markers = {"architecture", "how does", "design", "invariant", "tradeoff", "mechanism", "why", "compare"}
        if any(marker in text for marker in temporal_markers):
            return RetrievalMode.TEMPORAL.value
        if any(marker in text for marker in canonical_markers):
            return RetrievalMode.CANONICAL.value
        return RetrievalMode.MIXED.value
