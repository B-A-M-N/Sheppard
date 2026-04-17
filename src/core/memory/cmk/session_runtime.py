import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Iterable

from .types import CMKAtom
from .working_state import WorkingState, ActiveConcept, ActiveContradiction, SoftHypothesis
from .state_store import WorkingStateStore
from .intent_profiler import IntentProfiler
from .escalation_policy import EscalationPolicy, EscalationDecision

logger = logging.getLogger(__name__)

@dataclass
class SessionResult:
    route: str  # "chat" | "analysis"
    working_state: WorkingState
    working_brief: Optional[str] = None
    analysis_brief: Optional[str] = None
    analysis_result: Optional[Dict[str, Any]] = None
    escalation_reasons: Optional[list[str]] = None

class CognitiveSessionRuntime:
    """
    Cognitive middleware orchestrating the working-memory loop for each interaction turn.
    """
    
    def __init__(
        self,
        state_store: WorkingStateStore,
        intent_profiler: IntentProfiler,
        retriever,  # V3Retriever
        belief_graph,  # BeliefGraph
        escalation_policy: EscalationPolicy,
        analysis_service,  # AnalysisService
        cmk_runtime = None,
        salience_engine = None, # Future extension
        contradiction_monitor = None # Future extension
    ):
        self.state_store = state_store
        self.intent_profiler = intent_profiler
        self.retriever = retriever
        self.belief_graph = belief_graph
        self.escalation_policy = escalation_policy
        self.analysis_service = analysis_service
        self.cmk_runtime = cmk_runtime
        self.salience_engine = salience_engine
        self.contradiction_monitor = contradiction_monitor

    async def process_turn(
        self,
        session_id: str,
        user_text: str,
        agent_context: Optional[Dict[str, Any]] = None
    ) -> SessionResult:
        """
        Main cognitive loop for a conversational turn.
        """
        # 1. Load current session state
        state = await self.state_store.load(session_id)
        if not state:
            state = WorkingState(session_id=session_id)

        if agent_context:
            state.mission_id = agent_context.get("mission_id") or state.mission_id
            state.topic_id = agent_context.get("topic_id") or state.topic_id

        state.turn_index += 1

        # 2. Intent profiling
        intent = self.intent_profiler.profile(user_text, prior_state=state)
        state.intent_profile = intent
        self._update_state_from_intent(state, intent)

        retrieval_context = await self._retrieve_context(user_text, agent_context)
        if retrieval_context is not None:
            self._update_state_from_context(state, retrieval_context, user_text)
        self._update_state_from_runtime_signals(state)

        # 3. Decision: Escalate to deep reasoning?
        decision = self.escalation_policy.decide(state, user_text)
        state.escalation_level = decision.level

        # 4. Handle Route
        if decision.route == "analysis" and self.analysis_service:
            # Escalated path — invoke deliberate reasoning path
            analysis = await self.analysis_service.run_from_working_state(
                user_text=user_text,
                working_state=state
            )

            # Persist state before returning
            await self.state_store.save(state)

            return SessionResult(
                route="analysis",
                working_state=state,
                analysis_brief=self._build_analysis_brief(analysis, decision),
                analysis_result=analysis,
                escalation_reasons=decision.reasons,
            )

        # ── Conversational Path ──

        # 5. Build the working brief for prompt injection
        brief = self._build_working_brief(state, user_text)

        # 6. Persist state
        await self.state_store.save(state)

        return SessionResult(
            route="chat",
            working_state=state,
            working_brief=brief,
            escalation_reasons=decision.reasons,
        )

    def _update_state_from_intent(self, state: WorkingState, intent) -> None:
        state.candidate_frames = list(intent.candidate_frames)

        if intent.entities:
            state.recent_topics = list(dict.fromkeys((state.recent_topics + intent.entities)[-8:]))
            state.active_concepts = [
                ActiveConcept(
                    concept_id=f"entity:{entity.lower()}",
                    label=entity,
                    salience=max(0.4, 1.0 - (index * 0.15)),
                    source="query",
                )
                for index, entity in enumerate(intent.entities[:5])
            ]
        else:
            state.active_concepts = []

        state.confidence_pressure = max(
            0.0,
            min(
                1.0,
                0.55 * state.confidence_pressure
                + 0.30 * intent.risk_of_hallucination
                + 0.15 * intent.ambiguity_score,
            ),
        )
        state.insufficiency_pressure = max(
            0.0,
            min(
                1.0,
                0.60 * state.insufficiency_pressure
                + 0.25 * intent.ambiguity_score
                + 0.15 * (1.0 if intent.type == "exploratory" else 0.0),
            ),
        )

    async def _retrieve_context(
        self,
        user_text: str,
        agent_context: Optional[Dict[str, Any]],
    ):
        if not self.retriever:
            return None

        from src.research.reasoning.retriever import RetrievalQuery

        mission_id = agent_context.get("mission_id") if agent_context else None
        topic_id = agent_context.get("topic_id") if agent_context else None
        query = RetrievalQuery(
            text=user_text,
            mission_filter=mission_id,
            topic_filter=topic_id,
            project_filter=mission_id,
            max_results=8,
            max_contradictions=2,
            max_unresolved=2,
            max_project_artifacts=2,
        )
        try:
            return await self.retriever.retrieve(query)
        except Exception as exc:
            logger.debug("[CognitiveSessionRuntime] Retrieval probe failed: %s", exc)
            return None

    def _update_state_from_context(self, state: WorkingState, ctx, user_text: str) -> None:
        evidence = list(getattr(ctx, "evidence", []) or [])
        contradictions = list(getattr(ctx, "contradictions", []) or [])
        unresolved = list(getattr(ctx, "unresolved", []) or [])
        project_artifacts = list(getattr(ctx, "project_artifacts", []) or [])
        definitions = list(getattr(ctx, "definitions", []) or [])
        derived_contradictions = self._detect_runtime_contradictions(evidence)
        combined_contradictions = contradictions + [
            contradiction
            for contradiction in derived_contradictions
            if not any(
                str((existing.metadata or {}).get("contradiction_set_id") or existing.citation_key or existing.content)
                == str((contradiction.metadata or {}).get("contradiction_set_id") or contradiction.citation_key or contradiction.content)
                for existing in contradictions
            )
        ]

        state.active_atom_ids = self._extract_atom_ids(evidence[:8])
        state.active_derived_claim_ids = self._extract_citation_ids(definitions[:4])

        derived_concepts = self._build_active_concepts(
            state,
            evidence=evidence,
            project_artifacts=project_artifacts,
            definitions=definitions,
        )
        if derived_concepts:
            state.active_concepts = derived_concepts

        state.active_contradictions = [
            ActiveContradiction(
                contradiction_id=str(
                    (item.metadata or {}).get("contradiction_set_id")
                    or item.citation_key
                    or f"contradiction:{idx}"
                ),
                atom_ids=[
                    atom_id
                    for atom_id in (
                        (item.metadata or {}).get("atom_a_id"),
                        (item.metadata or {}).get("atom_b_id"),
                    )
                    if atom_id
                ],
                severity=min(1.0, max(0.35, float(getattr(item, "trust_score", 0.7)))),
                status="live",
                summary=item.content[:220],
            )
            for idx, item in enumerate(combined_contradictions[:3], start=1)
        ]

        state.soft_hypotheses = self._build_soft_hypotheses(unresolved, project_artifacts)

        trust_state = getattr(ctx, "aggregate_trust_state", "forming")
        contradiction_pressure = min(1.0, 0.35 * len(state.active_contradictions))
        unresolved_pressure = min(1.0, 0.25 * len(unresolved))
        trust_penalty = 0.2 if trust_state in {"contested", "forming"} else 0.0
        state.confidence_pressure = min(1.0, state.confidence_pressure + contradiction_pressure + trust_penalty)
        state.insufficiency_pressure = min(1.0, state.insufficiency_pressure + unresolved_pressure)

        self._record_runtime_probe(
            query_text=user_text,
            evidence=evidence,
            contradictions=state.active_contradictions,
            trust_state=trust_state,
        )

    def _update_state_from_runtime_signals(self, state: WorkingState) -> None:
        runtime = self.cmk_runtime
        if not runtime:
            return

        try:
            blind_spots = runtime.get_blind_spots()
        except Exception as exc:
            logger.debug("[CognitiveSessionRuntime] Blind-spot probe failed: %s", exc)
            blind_spots = []

        if blind_spots:
            top = blind_spots[0]
            severity = float(top.get("severity", 0.0) or 0.0)
            if top.get("type") in {"calibration_error", "error_pattern"}:
                state.confidence_pressure = min(1.0, state.confidence_pressure + min(0.2, severity * 0.2))
            else:
                state.insufficiency_pressure = min(1.0, state.insufficiency_pressure + min(0.15, severity * 0.15))

        if state.turn_index % 3 != 0 or state.soft_hypotheses:
            return

        try:
            hypotheses = runtime.generate_research_agenda(top_k=2)
        except Exception as exc:
            logger.debug("[CognitiveSessionRuntime] Hypothesis probe failed: %s", exc)
            hypotheses = []

        for hypothesis in hypotheses[:2]:
            hypothesis_id = hypothesis.get("description")
            if not hypothesis_id or any(existing.hypothesis_id == hypothesis_id for existing in state.soft_hypotheses):
                continue
            state.soft_hypotheses.append(
                SoftHypothesis(
                    hypothesis_id=hypothesis_id,
                    text=hypothesis.get("reason") or hypothesis.get("description") or "Potential missing relation",
                    confidence=float(hypothesis.get("priority", 0.5) or 0.5),
                )
            )
        state.soft_hypotheses = state.soft_hypotheses[:3]

    def _detect_runtime_contradictions(self, evidence) -> list[Any]:
        runtime = self.cmk_runtime
        detector = getattr(runtime, "contradiction_detector", None) if runtime else None
        if not detector:
            return []

        atoms = self._lift_items_to_cmk_atoms(evidence[:6])
        if len(atoms) < 2:
            return []

        try:
            contradictions = detector.detect(atoms, similarity_threshold=0.6)
        except Exception as exc:
            logger.debug("[CognitiveSessionRuntime] Contradiction probe failed: %s", exc)
            return []

        items = []
        for idx, contradiction in enumerate(contradictions[:2], start=1):
            atom_a = contradiction.get("atom_a")
            atom_b = contradiction.get("atom_b")
            description = contradiction.get("description") or "Potential contradiction detected"
            items.append(
                type(
                    "DerivedContradictionItem",
                    (),
                    {
                        "content": description,
                        "citation_key": f"derived-contradiction-{idx}",
                        "metadata": {
                            "atom_a_id": atom_a,
                            "atom_b_id": atom_b,
                            "type": contradiction.get("type", "derived"),
                        },
                        "trust_score": 0.65,
                    },
                )()
            )
        return items

    def _record_runtime_probe(
        self,
        query_text: str,
        evidence,
        contradictions: list[ActiveContradiction],
        trust_state: str,
    ) -> None:
        runtime = self.cmk_runtime
        if not runtime:
            return
        try:
            runtime.record_reasoning_step(
                step_type="retrieval",
                input_data={"query": query_text},
                output_data={
                    "evidence_count": len(evidence),
                    "contradiction_count": len(contradictions),
                    "trust_state": trust_state,
                },
                confidence=max(0.2, min(0.95, 1.0 - (0.15 * len(contradictions)))),
            )
        except Exception as exc:
            logger.debug("[CognitiveSessionRuntime] Meta-cognition record failed: %s", exc)

    def _build_active_concepts(self, state: WorkingState, evidence, project_artifacts, definitions) -> list[ActiveConcept]:
        labels: list[tuple[str, str, float]] = []

        for concept in state.active_concepts:
            labels.append((concept.concept_id, concept.label, concept.salience))

        for idx, item in enumerate(evidence[:4]):
            label = self._label_for_item(item)
            if label:
                labels.append((f"evidence:{idx}:{label.lower()}", label, max(0.45, float(getattr(item, "relevance_score", 0.5)))))

        for idx, item in enumerate(project_artifacts[:2]):
            label = self._label_for_item(item)
            if label:
                labels.append((f"artifact:{idx}:{label.lower()}", label, 0.6))

        for idx, item in enumerate(definitions[:2]):
            label = self._label_for_item(item)
            if label:
                labels.append((f"definition:{idx}:{label.lower()}", label, 0.55))

        deduped: dict[str, ActiveConcept] = {}
        for concept_id, label, salience in labels:
            key = label.lower()
            current = deduped.get(key)
            if current is None or salience > current.salience:
                deduped[key] = ActiveConcept(
                    concept_id=concept_id,
                    label=label,
                    salience=min(1.0, salience),
                    source="retrieval",
                )

        return sorted(deduped.values(), key=lambda item: item.salience, reverse=True)[:6]

    def _build_soft_hypotheses(self, unresolved, project_artifacts) -> list[SoftHypothesis]:
        hypotheses: list[SoftHypothesis] = []
        for idx, item in enumerate(unresolved[:2], start=1):
            hypotheses.append(
                SoftHypothesis(
                    hypothesis_id=str(item.citation_key or f"unresolved:{idx}"),
                    text=item.content[:220],
                    confidence=0.45,
                    support_atom_ids=self._extract_atom_ids([item]),
                )
            )
        for idx, item in enumerate(project_artifacts[:1], start=1):
            if len(hypotheses) >= 3:
                break
            hypotheses.append(
                SoftHypothesis(
                    hypothesis_id=str(item.citation_key or f"artifact:{idx}"),
                    text=f"Project artifact may contain relevant implementation evidence: {self._label_for_item(item)}",
                    confidence=0.4,
                    support_atom_ids=self._extract_atom_ids([item]),
                )
            )
        return hypotheses

    def _extract_atom_ids(self, items: Iterable[Any]) -> list[str]:
        atom_ids: list[str] = []
        for item in items:
            metadata = getattr(item, "metadata", None) or {}
            atom_id = metadata.get("atom_id")
            if atom_id and atom_id not in atom_ids:
                atom_ids.append(atom_id)
        return atom_ids

    def _extract_citation_ids(self, items: Iterable[Any]) -> list[str]:
        citation_ids: list[str] = []
        for item in items:
            citation_key = getattr(item, "citation_key", None)
            if citation_key and citation_key not in citation_ids:
                citation_ids.append(citation_key)
        return citation_ids

    def _lift_items_to_cmk_atoms(self, items: Iterable[Any]) -> list[CMKAtom]:
        atoms: list[CMKAtom] = []
        for item in items:
            metadata = getattr(item, "metadata", None) or {}
            atom_id = metadata.get("atom_id") or getattr(item, "citation_key", None)
            if not atom_id:
                continue
            contradicts = metadata.get("contradicts") or []
            if isinstance(contradicts, str):
                contradicts = [contradicts]
            atoms.append(
                CMKAtom(
                    id=str(atom_id),
                    content=getattr(item, "content", "") or "",
                    embedding=metadata.get("embedding"),
                    atom_type=getattr(item, "item_type", "claim") or "claim",
                    reliability=float(getattr(item, "trust_score", 0.5) or 0.5),
                    confidence=float(getattr(item, "trust_score", 0.5) or 0.5),
                    mission_id=metadata.get("mission_id", ""),
                    topic_id=metadata.get("topic_id", ""),
                    contradicts=[str(value) for value in contradicts if value],
                )
            )
        return atoms

    def _label_for_item(self, item: Any) -> str:
        metadata = getattr(item, "metadata", None) or {}
        for key in ("title", "canonical_title", "name", "authority_record_id", "citation_key"):
            value = metadata.get(key) or getattr(item, key, None)
            if isinstance(value, str) and value.strip():
                return value.strip()[:80]
        content = getattr(item, "content", "") or ""
        return content.split(":")[0].strip()[:80]

    def _build_working_brief(self, state: WorkingState, user_text: str) -> str:
        """
        Convert active cognitive state into a compact brief for prompt injection.
        """
        lines = []
        lines.append("### ACTIVE SESSION COGNITION")

        if state.intent_profile:
            lines.append(f"- INTENT: {state.intent_profile.primary_intent} ({state.intent_profile.type})")
            if state.intent_profile.candidate_frames:
                lines.append(f"- CANDIDATE FRAMES: {', '.join(state.intent_profile.candidate_frames)}")

        if state.active_concepts:
            concepts = [c.label for c in sorted(state.active_concepts, key=lambda x: x.salience, reverse=True)[:5]]
            lines.append(f"- SALIENT CONCEPTS: {', '.join(concepts)}")

        if state.active_contradictions:
            lines.append(f"- LIVE CONTRADICTIONS: {len(state.active_contradictions)} detected")
            for c in state.active_contradictions[:2]:
                lines.append(f"  * {c.summary}")

        if state.soft_hypotheses:
            lines.append("- HYPOTHESES:")
            for h in state.soft_hypotheses[:2]:
                lines.append(f"  * {h.text} (conf: {h.confidence:.2f})")

        # Confidence/Pressure hints
        if state.confidence_pressure > 0.5:
            lines.append("- GUIDANCE: Dampen certainty; conflicting evidence or high ambiguity detected.")
        if state.insufficiency_pressure > 0.5:
            lines.append("- GUIDANCE: Focus on gathering missing information; prior turns were inconclusive.")

        return "\n".join(lines)

    def _build_analysis_brief(
        self,
        analysis: Dict[str, Any],
        decision: EscalationDecision,
    ) -> str:
        lines = ["### ESCALATED ANALYSIS"]

        diagnosis = analysis.get("diagnosis")
        if diagnosis:
            lines.append(f"- DIAGNOSIS: {diagnosis}")

        recommendation = analysis.get("recommendation")
        if recommendation:
            lines.append(f"- RECOMMENDATION: {recommendation}")

        confidence = analysis.get("confidence")
        if isinstance(confidence, (int, float)):
            lines.append(f"- CONFIDENCE: {confidence:.2f}")

        trust_state = analysis.get("trust_state")
        if trust_state:
            lines.append(f"- TRUST STATE: {trust_state}")

        objection = analysis.get("objection")
        if objection:
            lines.append(f"- CRITIC: {objection}")

        if decision.reasons:
            lines.append(f"- ESCALATION BASIS: {'; '.join(decision.reasons[:3])}")

        return "\n".join(lines)
