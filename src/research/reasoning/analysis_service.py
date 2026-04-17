"""
reasoning/analysis_service.py

AnalysisService — orchestrates the full applied reasoning pipeline.

Flow:
  1. ProblemFramer parses the raw problem into structured dimensions
  2. Multi-query retrieval pulls targeted evidence for each retrieval query
  3. Evidence packets are merged into a single combined packet
  4. AnalystSynthAdapter reasons from the evidence to a position + recommendation
  5. AdversarialCritic challenges the Analyst's output using the same evidence
  6. AnalysisReport is assembled with formatted output for display

This is the /analyze equivalent of SynthesisService.generate_master_brief().
The library (Archivist) and the reasoning layer (Analyst) are independent —
both anchor to the same atoms, serve different purposes.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Optional, AsyncGenerator, Tuple, Any

from src.llm.client import OllamaClient
from src.research.reasoning.assembler import EvidencePacket, EvidenceAssembler, SectionPlan
from src.research.reasoning.problem_frame import ProblemFrame, ProblemFramer
from src.research.reasoning.analyst import AnalystOutput, AnalystSynthAdapter
from src.research.reasoning.adversarial_critic import CriticOutput, AdversarialCritic
from src.research.reasoning.retriever import RetrievalQuery
from src.research.reasoning.v3_retriever import V3Retriever
from src.research.reasoning.trust_state import derive_trust_state

logger = logging.getLogger(__name__)

# Atoms to retrieve per query (multiple queries are merged + deduplicated)
ATOMS_PER_QUERY = 12
# Maximum evidence token budget to feed into the Analyst
MAX_EVIDENCE_TOKENS = 12000


def _iter_text_lines(value: Any) -> List[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.split("\n") if line.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _build_report_trust_inputs(
    analyst: "AnalystOutput",
    critic: "CriticOutput",
    packet: Optional[Any] = None,
) -> tuple[dict, dict, dict]:
    """Canonical mapping from analyst+critic+packet → derive_trust_state inputs.

    Single source of truth for how a completed analysis report translates into
    the three trust-state input dicts.  Both the ephemeral AnalysisReport
    property and the authority-record persistence path call this function so
    the maturity classification logic is never duplicated.

    Returns:
        (status, advisory, reuse) suitable for derive_trust_state().
    """
    has_objection = bool(critic.strongest_objection)
    has_overlooked = bool(getattr(critic, "overlooked_atoms", []))
    has_contradictions = bool(getattr(packet, "contradictions", None) if packet else False)

    status: dict = {
        "freshness": "current",
        "maturity": (
            "contested"
            if (has_objection or has_overlooked or has_contradictions)
            else "synthesized"
        ),
        "successful_application_count": 1 if analyst.confidence >= 0.7 else 0,
    }
    advisory: dict = {
        "critic_objections": [critic.strongest_objection] if has_objection else [],
    }
    reuse: dict = {
        "ready_for_application": bool(
            analyst.recommendation and analyst.confidence >= 0.65
        ),
    }
    return status, advisory, reuse


@dataclass
class AnalysisReport:
    frame: ProblemFrame
    analyst: AnalystOutput
    critic: CriticOutput
    atom_count: int
    refined_analyst: Optional[AnalystOutput] = None
    mission_filter: Optional[str] = None
    application_query_id: Optional[str] = None

    @property
    def trust_state(self) -> str:
        status, advisory, reuse = _build_report_trust_inputs(self.refined_analyst or self.analyst, self.critic)
        return derive_trust_state(status, advisory, reuse)

    def formatted(self) -> str:
        """Human-readable formatted output for display in TUI."""
        lines = []

        # ── Header ──────────────────────────────────────────────────────────
        lines.append("━" * 60)
        lines.append("  ANALYSIS REPORT")
        lines.append("━" * 60)
        lines.append(f"  TRUST STATE: {self.trust_state.upper()}")

        # ── Problem understood ───────────────────────────────────────────────
        lines.append("")
        lines.append("PROBLEM UNDERSTOOD")
        if self.frame.goal:
            lines.append(f"  Goal:    {self.frame.goal}")
        if self.frame.symptoms:
            for s in self.frame.symptoms:
                lines.append(f"  Symptom: {s}")
        if self.frame.constraints:
            for c in self.frame.constraints:
                lines.append(f"  Constraint: {c}")
        lines.append(f"  Evidence base: {self.atom_count} atoms retrieved")

        # ── Diagnosis ────────────────────────────────────────────────────────
        lines.append("")
        final_analyst = self.refined_analyst or self.analyst
        conf_pct = f"{final_analyst.confidence:.0%}"
        lines.append(f"DIAGNOSIS  [{conf_pct} confidence]")
        lines.append(f"  {final_analyst.diagnosis}")

        # ── Reasoning ────────────────────────────────────────────────────────
        if final_analyst.reasoning:
            lines.append("")
            lines.append("REASONING")
            for para in _iter_text_lines(final_analyst.reasoning):
                lines.append(f"  {para}")

        # ── Alternatives ─────────────────────────────────────────────────────
        if final_analyst.alternatives:
            lines.append("")
            lines.append("ALTERNATIVES CONSIDERED")
            for alt in final_analyst.alternatives:
                likelihood = alt.get("likelihood", "?")
                explanation = alt.get("explanation", "")
                why_less = alt.get("why_less_likely", "")
                lines.append(f"  [{likelihood}] {explanation}")
                if why_less:
                    lines.append(f"        → less likely because: {why_less}")

        # ── Recommendation ───────────────────────────────────────────────────
        lines.append("")
        lines.append("RECOMMENDATION")
        lines.append(f"  {final_analyst.recommendation}")
        if final_analyst.recommendation_rationale:
            lines.append(f"  Rationale: {final_analyst.recommendation_rationale}")

        # ── Risks ────────────────────────────────────────────────────────────
        if final_analyst.risks:
            lines.append("")
            lines.append("FAILURE MODES  (how this breaks)")
            for risk in final_analyst.risks:
                lines.append(f"  • {risk}")

        # ── Open questions ───────────────────────────────────────────────────
        if final_analyst.open_questions:
            lines.append("")
            lines.append("OPEN QUESTIONS  (what would increase confidence)")
            for q in final_analyst.open_questions:
                lines.append(f"  ? {q}")

        if final_analyst.tensions:
            lines.append("")
            lines.append("TENSIONS")
            for tension in final_analyst.tensions:
                lines.append(f"  • {tension}")

        # ── Adversarial challenge ────────────────────────────────────────────
        lines.append("")
        lines.append("ADVERSARIAL CHALLENGE")
        lines.append(f"  {self.critic.strongest_objection}")

        if self.critic.overlooked_reasoning:
            lines.append("")
            lines.append("  Overlooked evidence:")
            lines.append(f"  {self.critic.overlooked_reasoning}")

        if self.critic.counter_recommendation:
            lines.append("")
            lines.append("  Counter-recommendation:")
            lines.append(f"  {self.critic.counter_recommendation}")
            if self.critic.counter_rationale:
                lines.append(f"  Why: {self.critic.counter_rationale}")

        if self.critic.synthesis:
            lines.append("")
            lines.append("  Key thing the Analyst didn't say:")
            lines.append(f"  {self.critic.synthesis}")

        if self.critic.confidence_assessment:
            lines.append("")
            lines.append(f"  Confidence check: {self.critic.confidence_assessment}")

        if final_analyst.revisions_applied:
            lines.append("")
            lines.append("REFINEMENTS APPLIED")
            for revision in final_analyst.revisions_applied:
                lines.append(f"  • {revision}")

        lines.append("")
        lines.append("━" * 60)

        return "\n".join(lines)


class AnalysisService:
    """
    Orchestrates the full problem analysis pipeline:
    framing → retrieval → analyst → critic → report.
    """

    def __init__(
        self,
        ollama: OllamaClient,
        retriever: V3Retriever,
        assembler: EvidenceAssembler,
    ):
        self.ollama = ollama
        self.retriever = retriever
        self.assembler = assembler
        self.framer = ProblemFramer(ollama)
        self.analyst = AnalystSynthAdapter(ollama)
        self.critic = AdversarialCritic(ollama)

    async def analyze(
        self,
        problem_statement: str,
        mission_filter: Optional[str] = None,
        topic_filter: Optional[str] = None,
    ) -> AnalysisReport:
        """
        Full analysis pipeline. Returns an AnalysisReport with formatted output.
        """
        report, packet = await self._run_analysis(
            problem_statement=problem_statement,
            mission_filter=mission_filter,
            topic_filter=topic_filter,
        )
        await self._persist_application_run(
            problem_statement=problem_statement,
            mission_filter=mission_filter,
            topic_filter=topic_filter,
            report=report,
            packet=packet,
        )
        return report

    async def analyze_stream(
        self,
        problem_statement: str,
        mission_filter: Optional[str] = None,
        topic_filter: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming version for TUI display. Yields progress lines as they happen,
        then yields the full formatted report at the end.
        """
        yield "Framing problem...\n"
        frame = await self.framer.frame(problem_statement)
        yield f"Problem type: {frame.problem_type} | {len(frame.retrieval_queries)} retrieval queries\n"

        yield "Retrieving evidence from knowledge base...\n"
        combined_packet = await self._multi_query_retrieve(
            frame=frame,
            mission_filter=mission_filter,
            topic_filter=topic_filter,
        )
        yield f"Evidence loaded: {len(combined_packet.atoms)} atoms\n"

        yield "Evidence map + analyst reasoning...\n"
        analyst_output = await self.analyst.analyze(combined_packet, frame)
        yield f"Draft confidence: {analyst_output.confidence:.0%}\n"

        yield "Adversarial critic reviewing...\n"
        critic_output = await self.critic.critique(analyst_output, combined_packet)
        yield "Refining analysis with critic feedback...\n"
        refined_output = await self.analyst.refine(combined_packet, frame, analyst_output, critic_output)
        preview_report = AnalysisReport(
            frame=frame,
            analyst=analyst_output,
            critic=critic_output,
            refined_analyst=refined_output,
            atom_count=len(combined_packet.atoms),
            mission_filter=mission_filter,
        )
        yield f"Trust state: {preview_report.trust_state}\n"

        report = AnalysisReport(
            frame=frame,
            analyst=analyst_output,
            critic=critic_output,
            refined_analyst=refined_output,
            atom_count=len(combined_packet.atoms),
            mission_filter=mission_filter,
        )
        await self._persist_application_run(
            problem_statement=problem_statement,
            mission_filter=mission_filter,
            topic_filter=topic_filter,
            report=report,
            packet=combined_packet,
        )

        yield "\n"
        yield report.formatted()

    async def _run_analysis(
        self,
        problem_statement: str,
        mission_filter: Optional[str],
        topic_filter: Optional[str],
    ) -> Tuple[AnalysisReport, EvidencePacket]:
        # 1. Frame the problem
        logger.info("[AnalysisService] Framing problem: %s", problem_statement[:80])
        frame = await self.framer.frame(problem_statement)
        logger.info(
            "[AnalysisService] Frame: type=%s, queries=%d, domains=%s",
            frame.problem_type,
            len(frame.retrieval_queries),
            frame.domain_hints,
        )

        # 2. Multi-query retrieval — run all queries concurrently, merge results
        logger.info("[AnalysisService] Running %d retrieval queries", len(frame.all_retrieval_queries()))
        combined_packet = await self._multi_query_retrieve(
            frame=frame,
            mission_filter=mission_filter,
            topic_filter=topic_filter,
        )
        weak_dimensions = self._detect_weak_dimensions(frame, combined_packet)
        if weak_dimensions:
            logger.info("[AnalysisService] Coverage gaps detected in dimensions: %s", weak_dimensions)
            follow_up_queries = self.framer.follow_up_for_dimensions(frame, weak_dimensions)
            if follow_up_queries:
                combined_packet = await self._multi_query_retrieve(
                    frame=ProblemFrame(
                        raw_statement=frame.raw_statement,
                        problem=frame.problem,
                        symptoms=frame.symptoms,
                        goal=frame.goal,
                        constraints=frame.constraints,
                        dimensions=frame.dimensions,
                        unknowns=frame.unknowns,
                        domain_hints=frame.domain_hints,
                        retrieval_queries=follow_up_queries,
                        problem_type=frame.problem_type,
                        retrieval_mode=frame.retrieval_mode,
                    ),
                    mission_filter=mission_filter,
                    topic_filter=topic_filter,
                )
        logger.info("[AnalysisService] Combined evidence: %d atoms", len(combined_packet.atoms))

        # 3. Analyst — reason from evidence to a position
        analyst_output = await self.analyst.analyze(combined_packet, frame)
        logger.info(
            "[AnalysisService] Analyst: confidence=%.0f%%, recommendation=%s",
            analyst_output.confidence * 100,
            analyst_output.recommendation[:60] if analyst_output.recommendation else "none",
        )

        # 4. Adversarial Critic — challenge the Analyst
        critic_output = await self.critic.critique(analyst_output, combined_packet)
        logger.info("[AnalysisService] Critic complete")
        refined_output = await self.analyst.refine(combined_packet, frame, analyst_output, critic_output)
        logger.info("[AnalysisService] Refinement complete")

        report = AnalysisReport(
            frame=frame,
            analyst=analyst_output,
            critic=critic_output,
            refined_analyst=refined_output,
            atom_count=len(combined_packet.atoms),
            mission_filter=mission_filter,
        )
        return report, combined_packet

    async def run_from_working_state(
        self,
        user_text: str,
        working_state: Any, # Avoid circular import of WorkingState
    ) -> dict:
        """
        Escalation path: Run a full analysis grounded in the current working state.
        Returns a simplified dictionary for chat integration.
        """
        logger.info("[AnalysisService] Running escalated analysis from working state")
        
        # 1. Frame the problem (optionally use hints from working state)
        frame = await self.framer.frame(user_text)
        
        # Update frame with hints from working state if available
        candidate_frames = list(
            dict.fromkeys(
                (getattr(working_state, "candidate_frames", None) or [])
                + (
                    getattr(getattr(working_state, "intent_profile", None), "candidate_frames", None)
                    or []
                )
            )
        )
        if candidate_frames:
            frame.domain_hints = list(dict.fromkeys(frame.domain_hints + candidate_frames))
            
        # 2. Retrieval
        mission_filter = getattr(working_state, "mission_id", None)
        topic_filter = getattr(working_state, "topic_id", None)
        
        combined_packet = await self._multi_query_retrieve(
            frame=frame,
            mission_filter=mission_filter,
            topic_filter=topic_filter,
        )
        
        # 3. Analyst
        analyst_output = await self.analyst.analyze(combined_packet, frame)
        
        # 4. Critic
        critic_output = await self.critic.critique(analyst_output, combined_packet)
        refined_output = await self.analyst.refine(combined_packet, frame, analyst_output, critic_output)
        
        # 5. Persist the run
        report = AnalysisReport(
            frame=frame,
            analyst=analyst_output,
            critic=critic_output,
            refined_analyst=refined_output,
            atom_count=len(combined_packet.atoms),
            mission_filter=mission_filter,
        )
        
        await self._persist_application_run(
            problem_statement=user_text,
            mission_filter=mission_filter,
            topic_filter=topic_filter,
            report=report,
            packet=combined_packet,
        )
        
        # Return summary for chat
        return {
            "diagnosis": refined_output.diagnosis,
            "recommendation": refined_output.recommendation,
            "confidence": refined_output.confidence,
            "objection": critic_output.strongest_objection,
            "counter_recommendation": critic_output.counter_recommendation,
            "atom_count": len(combined_packet.atoms),
            "trust_state": report.trust_state
        }

    async def _persist_application_run(
        self,
        problem_statement: str,
        mission_filter: Optional[str],
        topic_filter: Optional[str],
        report: AnalysisReport,
        packet: EvidencePacket,
    ) -> None:
        adapter = getattr(self.assembler, "adapter", None) or getattr(self.retriever, "adapter", None)
        if not adapter:
            return
        final_analyst = getattr(report, "refined_analyst", None) or report.analyst

        application_query_id = f"aq_{uuid.uuid4().hex[:12]}"
        report.application_query_id = application_query_id

        payload = {
            "problem_type": report.frame.problem_type,
            "goal": report.frame.goal,
            "symptoms": report.frame.symptoms,
            "constraints": report.frame.constraints,
            "domain_hints": report.frame.domain_hints,
            "retrieval_queries": report.frame.retrieval_queries,
            "mission_filter": mission_filter,
            "topic_filter": topic_filter,
            "atom_count": len(packet.atoms),
            "contradiction_count": len(packet.contradictions),
            "key_atoms": final_analyst.key_atoms,
            "critic_overlooked_atoms": report.critic.overlooked_atoms,
            "graph_summary": self._graph_summary(packet),
        }

        try:
            await adapter.create_application_query({
                "application_query_id": application_query_id,
                "project_id": mission_filter or topic_filter,
                "query_type": "analysis",
                "title": report.frame.goal or problem_statement[:120],
                "problem_statement": problem_statement,
                "payload_json": payload,
            })
            await adapter.store_application_output({
                "application_query_id": application_query_id,
                "output_type": "analysis_report",
                "inline_text": report.formatted(),
                "confidence": final_analyst.confidence,
                "metadata_json": {
                    "diagnosis": final_analyst.diagnosis,
                    "recommendation": final_analyst.recommendation,
                    "critic_objection": report.critic.strongest_objection,
                    "counter_recommendation": report.critic.counter_recommendation,
                },
            })
            if final_analyst.risks:
                await adapter.store_application_output({
                    "application_query_id": application_query_id,
                    "output_type": "analysis_risk_register",
                    "inline_text": "\n".join(final_analyst.risks),
                    "confidence": final_analyst.confidence,
                    "metadata_json": {"risks": final_analyst.risks},
                })
            if report.critic.strongest_objection:
                await adapter.store_application_output({
                    "application_query_id": application_query_id,
                    "output_type": "critic_challenge",
                    "inline_text": report.critic.strongest_objection,
                    "confidence": final_analyst.confidence,
                    "metadata_json": {
                        "strongest_objection": report.critic.strongest_objection,
                        "overlooked_reasoning": report.critic.overlooked_reasoning,
                        "counter_recommendation": report.critic.counter_recommendation,
                        "confidence_assessment": report.critic.confidence_assessment,
                    },
                })
            graph_summary = self._graph_summary(packet)
            if graph_summary["node_count"] > 0:
                await adapter.store_application_output({
                    "application_query_id": application_query_id,
                    "output_type": "analysis_graph_summary",
                    "inline_text": self._format_graph_summary(graph_summary),
                    "confidence": final_analyst.confidence,
                    "metadata_json": graph_summary,
                })
            if final_analyst.open_questions:
                await adapter.store_application_output({
                    "application_query_id": application_query_id,
                    "output_type": "analysis_open_questions",
                    "inline_text": "\n".join(final_analyst.open_questions),
                    "confidence": final_analyst.confidence,
                    "metadata_json": {"open_questions": final_analyst.open_questions},
                })
            await adapter.store_application_lineage(
                application_query_id,
                {
                    "frame": {
                        "problem_type": report.frame.problem_type,
                        "goal": report.frame.goal,
                        "symptoms": report.frame.symptoms,
                        "constraints": report.frame.constraints,
                        "domain_hints": report.frame.domain_hints,
                        "retrieval_queries": report.frame.retrieval_queries,
                    },
                    "analyst": {
                        "diagnosis": final_analyst.diagnosis,
                        "confidence": final_analyst.confidence,
                        "recommendation": final_analyst.recommendation,
                        "key_atoms": final_analyst.key_atoms,
                        "revisions_applied": final_analyst.revisions_applied,
                    },
                    "critic": {
                        "strongest_objection": report.critic.strongest_objection,
                        "counter_recommendation": report.critic.counter_recommendation,
                        "overlooked_atoms": report.critic.overlooked_atoms,
                    },
                    "graph_summary": graph_summary,
                    "section_guidance": packet.section_guidance,
                },
            )

            evidence_rows = []
            seen = set()
            for atom in packet.atoms:
                metadata = atom.get("metadata") or {}
                row = {
                    "authority_record_id": metadata.get("authority_record_id"),
                    "atom_id": metadata.get("atom_id"),
                    "bundle_id": None,
                }
                if not row["authority_record_id"] and not row["atom_id"]:
                    continue
                dedup_key = (row["authority_record_id"], row["atom_id"], row["bundle_id"])
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                evidence_rows.append(row)

            if evidence_rows:
                await adapter.bind_application_evidence(application_query_id, evidence_rows)
                await self._persist_authority_feedback(
                    adapter=adapter,
                    application_query_id=application_query_id,
                    report=report,
                    packet=packet,
                    evidence_rows=evidence_rows,
                )
        except Exception as exc:
            logger.warning("[AnalysisService] Failed to persist application run: %s", exc)

    async def _persist_authority_feedback(
        self,
        adapter: Any,
        application_query_id: str,
        report: AnalysisReport,
        packet: EvidencePacket,
        evidence_rows: list[dict[str, Any]],
    ) -> None:
        final_analyst = getattr(report, "refined_analyst", None) or report.analyst
        authority_ids = sorted({
            row["authority_record_id"]
            for row in evidence_rows
            if row.get("authority_record_id")
        })
        if not authority_ids:
            return

        timestamp = datetime.now(timezone.utc).isoformat()
        packet_atoms_by_citation = {
            self._normalize_citation(atom.get("global_id")): atom
            for atom in packet.atoms
            if atom.get("global_id")
        }
        key_atoms = [
            packet_atoms_by_citation[citation]
            for citation in (self._normalize_citation(value) for value in final_analyst.key_atoms)
            if citation in packet_atoms_by_citation
        ]
        overlooked_atoms = [
            packet_atoms_by_citation[citation]
            for citation in (self._normalize_citation(value) for value in report.critic.overlooked_atoms)
            if citation in packet_atoms_by_citation
        ]

        co_cited_ids = set(authority_ids)
        for authority_record_id in authority_ids:
            existing = {}
            if hasattr(adapter, "get_authority_record"):
                existing = await adapter.get_authority_record(authority_record_id) or {}
            status = self._parse_json_field(existing.get("status_json") or existing.get("status"))
            advisory = self._parse_json_field(existing.get("advisory_layer_json") or existing.get("advisory_layer"))
            reuse = self._parse_json_field(existing.get("reuse_json") or existing.get("reuse"))

            advisory["application_feedback"] = {
                "last_application_query_id": application_query_id,
                "last_diagnosis": final_analyst.diagnosis,
                "last_recommendation": final_analyst.recommendation,
                "recent_risks": final_analyst.risks,
                "critic_objection": report.critic.strongest_objection,
                "open_questions": final_analyst.open_questions,
                "updated_at": timestamp,
                "graph_summary": self._graph_summary(packet),
            }
            if key_atoms:
                advisory["decision_rules"] = self._merge_unique_text(
                    advisory.get("decision_rules", []),
                    [final_analyst.recommendation_rationale or final_analyst.recommendation],
                )
            if final_analyst.risks:
                advisory["risk_register"] = self._merge_unique_text(
                    advisory.get("risk_register", []),
                    final_analyst.risks,
                )
            if report.critic.strongest_objection:
                advisory["critic_objections"] = self._merge_unique_text(
                    advisory.get("critic_objections", []),
                    [report.critic.strongest_objection],
                )
            if packet.section_guidance:
                advisory["section_guidance"] = packet.section_guidance[:4]

            reuse_history = reuse.get("application_history", [])
            reuse_history.append({
                "application_query_id": application_query_id,
                "problem_type": report.frame.problem_type,
                "recommendation": final_analyst.recommendation,
                "confidence": final_analyst.confidence,
                "timestamp": timestamp,
            })
            reuse["application_history"] = reuse_history[-10:]
            reuse["last_application_query_id"] = application_query_id
            reuse["last_recommendation"] = final_analyst.recommendation
            reuse["key_atom_ids"] = self._merge_unique_text(
                reuse.get("key_atom_ids", []),
                [atom.get("metadata", {}).get("atom_id") for atom in key_atoms],
            )
            reuse["critic_overlooked_atom_ids"] = self._merge_unique_text(
                reuse.get("critic_overlooked_atom_ids", []),
                [atom.get("metadata", {}).get("atom_id") for atom in overlooked_atoms],
            )
            related_ids = sorted(co_cited_ids - {authority_record_id})
            if related_ids:
                reuse["related_authority_record_ids"] = related_ids

            status["application_count"] = int(status.get("application_count", 0) or 0) + 1
            status["last_applied_at"] = timestamp
            status["last_application_query_id"] = application_query_id
            status["latest_analysis_confidence"] = final_analyst.confidence
            status["has_critic_review"] = True
            status.setdefault("freshness", "current")
            prior_authority = float(status.get("authority_score", 0.0) or 0.0)
            confidence_gain = max(0.0, min(0.12, final_analyst.confidence * 0.08))
            status["authority_score"] = round(min(1.0, prior_authority + confidence_gain), 4)
            status["successful_application_count"] = int(status.get("successful_application_count", 0) or 0) + 1
            # Use canonical builder to determine maturity from report signals —
            # the same logic as AnalysisReport.trust_state (via _build_report_trust_inputs).
            report_status, _, _ = _build_report_trust_inputs(final_analyst, report.critic, packet)
            if report_status["maturity"] == "contested":
                status["maturity"] = "contested"
            status["trust_state"] = derive_trust_state(status, advisory, reuse)

            update_row = {
                "authority_record_id": authority_record_id,
                "topic_id": existing.get("topic_id"),
                "domain_profile_id": existing.get("domain_profile_id"),
                "title": existing.get("title"),
                "canonical_title": existing.get("canonical_title"),
                "scope_json": self._parse_json_field(existing.get("scope_json") or existing.get("scope")),
                "frontier_summary_json": self._parse_json_field(existing.get("frontier_summary_json") or existing.get("frontier_summary")),
                "corpus_layer_json": self._parse_json_field(existing.get("corpus_layer_json") or existing.get("corpus_layer")),
                "atom_layer_json": self._parse_json_field(existing.get("atom_layer_json") or existing.get("atom_layer")),
                "synthesis_layer_json": self._parse_json_field(existing.get("synthesis_layer_json") or existing.get("synthesis_layer")),
                "lineage_layer_json": self._parse_json_field(existing.get("lineage_layer_json") or existing.get("lineage_layer")),
                "status_json": status,
                "advisory_layer_json": advisory,
                "reuse_json": reuse,
            }
            await adapter.upsert_authority_record(update_row)

    @staticmethod
    def _normalize_citation(value: Optional[str]) -> str:
        if not value:
            return ""
        text = value.strip()
        if not text:
            return ""
        if not text.startswith("["):
            text = f"[{text}]"
        return text

    @staticmethod
    def _parse_json_field(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _merge_unique_text(existing: list[Any], incoming: list[Any]) -> list[Any]:
        merged = []
        seen = set()
        for value in [*(existing or []), *(incoming or [])]:
            if not value:
                continue
            if value in seen:
                continue
            seen.add(value)
            merged.append(value)
        return merged

    @staticmethod
    def _graph_summary(packet: EvidencePacket) -> dict[str, Any]:
        graph = getattr(packet, "evidence_graph", None)
        if not graph:
            return {"node_count": 0, "edge_count": 0, "contradiction_nodes": 0, "guidance_count": 0}
        contradiction_nodes = sum(
            1 for node in graph.nodes.values()
            if getattr(node, "node_type", None) == "contradiction"
        )
        return {
            "node_count": len(getattr(graph, "nodes", {})),
            "edge_count": len(getattr(graph, "edges", {})),
            "contradiction_nodes": contradiction_nodes,
            "guidance_count": len(getattr(packet, "section_guidance", []) or []),
        }

    @staticmethod
    def _format_graph_summary(summary: dict[str, Any]) -> str:
        return (
            f"Graph nodes: {summary['node_count']}, "
            f"edges: {summary['edge_count']}, "
            f"contradictions: {summary['contradiction_nodes']}, "
            f"guidance plans: {summary['guidance_count']}"
        )

    async def _multi_query_retrieve(
        self,
        frame: ProblemFrame,
        mission_filter: Optional[str],
        topic_filter: Optional[str],
    ) -> EvidencePacket:
        """
        Run all retrieval queries concurrently. Merge + deduplicate atoms.
        Returns a single combined EvidencePacket.
        """
        queries = frame.all_retrieval_queries()

        async def _retrieve_one(query_text: str) -> List[dict]:
            q = RetrievalQuery(
                text=query_text,
                mission_filter=mission_filter,
                topic_filter=topic_filter,
                max_results=ATOMS_PER_QUERY,
                retrieval_mode=frame.retrieval_mode,
            )
            try:
                ctx = await self.retriever.retrieve(q)
                atoms = []
                seen = set()
                for idx, item in enumerate(ctx.all_items):
                    aid = item.metadata.get("atom_id") if item.metadata else None
                    dedup_key = aid or item.content[:80]
                    if dedup_key not in seen:
                        seen.add(dedup_key)
                        atoms.append({
                            "global_id": item.citation_key or f"[A{idx+1}]",
                            "text": item.content,
                            "type": item.item_type,
                            "confidence": item.trust_score,
                            "metadata": item.metadata or {},
                        })
                return atoms
            except Exception as exc:
                logger.warning("[AnalysisService] Retrieval failed for query '%s': %s", query_text[:40], exc)
                return []

        # Concurrent retrieval across all queries
        results = await asyncio.gather(*[_retrieve_one(q) for q in queries])

        merged: dict[str, dict] = {}
        for batch in results:
            for atom in batch:
                gid = atom["global_id"]
                if gid not in merged:
                    merged[gid] = atom

        packed_atoms = self._pack_evidence(list(merged.values()), max_tokens=MAX_EVIDENCE_TOKENS)
        logger.info(
            "[AnalysisService] evidence_packing atoms_in=%d atoms_out=%d packed_tokens=%d token_budget=%d",
            len(merged),
            len(packed_atoms),
            sum(self._estimate_tokens(atom.get("text", "")) for atom in packed_atoms),
            MAX_EVIDENCE_TOKENS,
        )

        combined = EvidencePacket(
            topic_name=frame.raw_statement,
            section_title="Combined Analysis Evidence",
            section_objective=frame.goal or frame.raw_statement,
            atoms=packed_atoms,
        )

        # Pull contradictions via the assembler's existing method
        try:
            contradiction_scope = mission_filter or topic_filter
            if contradiction_scope and hasattr(self.assembler, '_get_unresolved_contradictions'):
                contradictions = await self.assembler._get_unresolved_contradictions(
                    contradiction_scope, limit=8
                )
                for c in contradictions:
                    typed = self.retriever._classify_contradiction(
                        c.get("atom_a_content", ""),
                        c.get("atom_b_content", ""),
                    ) if hasattr(self.retriever, "_classify_contradiction") else {}
                    combined.contradictions.append({
                        "description": c.get("description", ""),
                        "claim_a": c.get("atom_a_content", ""),
                        "claim_b": c.get("atom_b_content", ""),
                        **typed,
                    })
                logger.info("[AnalysisService] unresolved_contradictions count=%d", len(combined.contradictions))
        except Exception as exc:
            logger.debug("[AnalysisService] Could not retrieve contradictions: %s", exc)

        return combined

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len((text or "").split()))

    def _pack_evidence(self, atoms: List[dict], max_tokens: int) -> List[dict]:
        clusters: dict[str, List[dict]] = {
            "contradiction": [],
            "mechanism": [],
            "tradeoffs": [],
            "constraints": [],
            "implementation": [],
            "other": [],
        }
        for atom in atoms:
            text = (atom.get("text") or "").lower()
            atype = (atom.get("type") or "").lower()
            if "contradiction" in atype:
                clusters["contradiction"].append(atom)
            elif any(token in text for token in ("because", "causes", "mechanism", "works", "root cause")):
                clusters["mechanism"].append(atom)
            elif any(token in text for token in ("tradeoff", "versus", "compare", "better", "worse")):
                clusters["tradeoffs"].append(atom)
            elif any(token in text for token in ("constraint", "limit", "bound", "cannot", "must")):
                clusters["constraints"].append(atom)
            elif any(token in text for token in ("implement", "deploy", "config", "code", "runtime")):
                clusters["implementation"].append(atom)
            else:
                clusters["other"].append(atom)

        ordered: List[dict] = []
        cluster_names = ["contradiction", "mechanism", "tradeoffs", "constraints", "implementation", "other"]
        indices = {name: 0 for name in cluster_names}
        while True:
            added = False
            for name in cluster_names:
                cluster = clusters[name]
                idx = indices[name]
                if idx < len(cluster):
                    ordered.append(cluster[idx])
                    indices[name] += 1
                    added = True
            if not added:
                break

        packed: List[dict] = []
        used_tokens = 0
        for atom in ordered:
            atom_tokens = self._estimate_tokens(atom.get("text", ""))
            if packed and used_tokens + atom_tokens > max_tokens:
                break
            packed.append(atom)
            used_tokens += atom_tokens
        return packed

    @staticmethod
    def _detect_weak_dimensions(frame: ProblemFrame, packet: EvidencePacket) -> List[str]:
        weak: List[str] = []
        joined = "\n".join(atom.get("text", "") for atom in packet.atoms).lower()
        for dimension in frame.dimensions:
            if dimension == "failure_modes" and not packet.contradictions:
                weak.append(dimension)
                continue
            if dimension not in joined:
                weak.append(dimension)
        if weak:
            logger.info("[AnalysisService] follow_up_query_trigger weak_dimensions=%s", ",".join(weak[:3]))
        return weak[:3]
