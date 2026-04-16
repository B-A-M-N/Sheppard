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
import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, AsyncGenerator, Tuple

from src.llm.client import OllamaClient
from src.research.reasoning.assembler import EvidencePacket, EvidenceAssembler, SectionPlan
from src.research.reasoning.problem_frame import ProblemFrame, ProblemFramer
from src.research.reasoning.analyst import AnalystOutput, AnalystSynthAdapter
from src.research.reasoning.adversarial_critic import CriticOutput, AdversarialCritic
from src.research.reasoning.retriever import RetrievalQuery
from src.research.reasoning.v3_retriever import V3Retriever

logger = logging.getLogger(__name__)

# Atoms to retrieve per query (multiple queries are merged + deduplicated)
ATOMS_PER_QUERY = 12
# Maximum total atoms to feed into the Analyst
MAX_COMBINED_ATOMS = 40


@dataclass
class AnalysisReport:
    frame: ProblemFrame
    analyst: AnalystOutput
    critic: CriticOutput
    atom_count: int
    mission_filter: Optional[str] = None
    application_query_id: Optional[str] = None

    def formatted(self) -> str:
        """Human-readable formatted output for display in TUI."""
        lines = []

        # ── Header ──────────────────────────────────────────────────────────
        lines.append("━" * 60)
        lines.append("  ANALYSIS REPORT")
        lines.append("━" * 60)

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
        conf_pct = f"{self.analyst.confidence:.0%}"
        lines.append(f"DIAGNOSIS  [{conf_pct} confidence]")
        lines.append(f"  {self.analyst.diagnosis}")

        # ── Reasoning ────────────────────────────────────────────────────────
        if self.analyst.reasoning:
            lines.append("")
            lines.append("REASONING")
            for para in self.analyst.reasoning.split("\n"):
                if para.strip():
                    lines.append(f"  {para.strip()}")

        # ── Alternatives ─────────────────────────────────────────────────────
        if self.analyst.alternatives:
            lines.append("")
            lines.append("ALTERNATIVES CONSIDERED")
            for alt in self.analyst.alternatives:
                likelihood = alt.get("likelihood", "?")
                explanation = alt.get("explanation", "")
                why_less = alt.get("why_less_likely", "")
                lines.append(f"  [{likelihood}] {explanation}")
                if why_less:
                    lines.append(f"        → less likely because: {why_less}")

        # ── Recommendation ───────────────────────────────────────────────────
        lines.append("")
        lines.append("RECOMMENDATION")
        lines.append(f"  {self.analyst.recommendation}")
        if self.analyst.recommendation_rationale:
            lines.append(f"  Rationale: {self.analyst.recommendation_rationale}")

        # ── Risks ────────────────────────────────────────────────────────────
        if self.analyst.risks:
            lines.append("")
            lines.append("FAILURE MODES  (how this breaks)")
            for risk in self.analyst.risks:
                lines.append(f"  • {risk}")

        # ── Open questions ───────────────────────────────────────────────────
        if self.analyst.open_questions:
            lines.append("")
            lines.append("OPEN QUESTIONS  (what would increase confidence)")
            for q in self.analyst.open_questions:
                lines.append(f"  ? {q}")

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

        yield "Analyst reasoning...\n"
        analyst_output = await self.analyst.analyze(combined_packet, frame)
        yield f"Diagnosis confidence: {analyst_output.confidence:.0%}\n"

        yield "Adversarial critic reviewing...\n"
        critic_output = await self.critic.critique(analyst_output, combined_packet)

        report = AnalysisReport(
            frame=frame,
            analyst=analyst_output,
            critic=critic_output,
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

        report = AnalysisReport(
            frame=frame,
            analyst=analyst_output,
            critic=critic_output,
            atom_count=len(combined_packet.atoms),
            mission_filter=mission_filter,
        )
        return report, combined_packet

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
            "key_atoms": report.analyst.key_atoms,
            "critic_overlooked_atoms": report.critic.overlooked_atoms,
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
                "confidence": report.analyst.confidence,
                "metadata_json": {
                    "diagnosis": report.analyst.diagnosis,
                    "recommendation": report.analyst.recommendation,
                    "critic_objection": report.critic.strongest_objection,
                    "counter_recommendation": report.critic.counter_recommendation,
                },
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
                        "diagnosis": report.analyst.diagnosis,
                        "confidence": report.analyst.confidence,
                        "recommendation": report.analyst.recommendation,
                        "key_atoms": report.analyst.key_atoms,
                    },
                    "critic": {
                        "strongest_objection": report.critic.strongest_objection,
                        "counter_recommendation": report.critic.counter_recommendation,
                        "overlooked_atoms": report.critic.overlooked_atoms,
                    },
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
        except Exception as exc:
            logger.warning("[AnalysisService] Failed to persist application run: %s", exc)

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

        # Merge: deduplicate by global_id, cap at MAX_COMBINED_ATOMS
        merged: dict[str, dict] = {}
        for batch in results:
            for atom in batch:
                gid = atom["global_id"]
                if gid not in merged:
                    merged[gid] = atom
                if len(merged) >= MAX_COMBINED_ATOMS:
                    break

        combined = EvidencePacket(
            topic_name=frame.raw_statement,
            section_title="Combined Analysis Evidence",
            section_objective=frame.goal or frame.raw_statement,
            atoms=list(merged.values()),
        )

        # Pull contradictions via the assembler's existing method
        try:
            contradiction_scope = mission_filter or topic_filter
            if contradiction_scope and hasattr(self.assembler, '_get_unresolved_contradictions'):
                contradictions = await self.assembler._get_unresolved_contradictions(
                    contradiction_scope, limit=8
                )
                for c in contradictions:
                    combined.contradictions.append({
                        "description": c.get("description", ""),
                        "claim_a": c.get("atom_a_content", ""),
                        "claim_b": c.get("atom_b_content", ""),
                    })
        except Exception as exc:
            logger.debug("[AnalysisService] Could not retrieve contradictions: %s", exc)

        return combined
