import logging
import hashlib
from typing import Optional, Dict, Any

from .runtime import CMKRuntime
from .config import CMKConfig
from .intent_profiler import IntentProfile
from .loop_governor import LoopGovernor, CompressedContext

# Session Memory Layer
from .state_store import WorkingStateStore
from .escalation_policy import EscalationPolicy
from .session_runtime import CognitiveSessionRuntime, SessionResult

logger = logging.getLogger(__name__)


class CMKChatBridge:
    """
    Bridges CMK into Sheppard's live chat path.
    Integrates session-scoped cognitive state with long-term memory retrieval.
    """

    def __init__(
        self,
        redis_client=None,
        pg_pool=None,
        ollama_host: str = "http://localhost:11434",
        ollama_embed_model: str = "nomic-embed-text",
        distillation_pipeline=None,
        retriever=None,
        analysis_service=None
    ):
        config = CMKConfig.from_env()
        config.embedding.host = ollama_host
        config.embedding.model = ollama_embed_model

        self.runtime = CMKRuntime(
            config=config,
            redis_client=redis_client,
            pg_pool=pg_pool,
        )
        self.governor = LoopGovernor()
        self.distillation_pipeline = distillation_pipeline
        self.retriever = retriever
        self.analysis_service = analysis_service
        self._initialized = False
        
        # ── Cognitive Session Components ──
        self.state_store = WorkingStateStore(redis_client)
        self.escalation_policy = EscalationPolicy()
        self.session_runtime = None

    def attach_runtime_dependencies(self, retriever=None, analysis_service=None) -> None:
        self.retriever = retriever or self.retriever
        self.analysis_service = analysis_service or self.analysis_service

        if self.session_runtime:
            self.session_runtime.retriever = self.retriever
            self.session_runtime.analysis_service = self.analysis_service

    async def initialize(self) -> bool:
        """Load concepts from store, verify embeddings available."""
        try:
            count = await self.runtime.load_concepts()
            
            # Initialize CognitiveSessionRuntime
            self.session_runtime = CognitiveSessionRuntime(
                state_store=self.state_store,
                intent_profiler=self.runtime.intent_profiler,
                retriever=self.retriever,
                belief_graph=self.runtime.belief_graph,
                escalation_policy=self.escalation_policy,
                analysis_service=self.analysis_service,
                cmk_runtime=self.runtime,
            )
            
            self._initialized = True
            logger.info(f"[CMKChatBridge] Initialized: {count} concepts loaded")
            return True
        except Exception as e:
            logger.error(f"[CMKChatBridge] Init failed: {e}")
            return False

    async def query_with_cmk(
        self,
        user_query: str,
        session_id: Optional[str] = None,
        topic_filter: Optional[str] = None,
        mission_filter: Optional[str] = None,
        use_concepts: bool = True,
        use_reasoning: bool = True,
    ) -> Dict[str, Any]:
        """
        Comprehensive CMK query — integrates session state with retrieval.
        
        This method maintains backward compatibility with the original return
        contract while adding session-scoped cognitive continuity.
        """
        if not self._initialized:
            await self.initialize()

        # 1. Derive/Load Session State
        if not session_id:
            raw_id = f"{mission_filter or 'default'}:{user_query[:50]}"
            session_id = hashlib.md5(raw_id.encode()).hexdigest()

        # Process turn through cognitive session runtime (intent, escalation, state update)
        session_result = await self.session_runtime.process_turn(
            session_id=session_id,
            user_text=user_query,
            agent_context={"mission_id": mission_filter, "topic_id": topic_filter}
        )

        if session_result.route == "analysis":
            return {
                "evidence_pack": None,
                "intent": session_result.working_state.intent_profile,
                "plan": None,
                "working_brief": session_result.working_brief,
                "analysis_brief": session_result.analysis_brief,
                "analysis_result": session_result.analysis_result,
                "route": session_result.route,
                "compressed_context": None,
                "governor_decisions": [],
                "reasoning_context": None,
                "session_id": session_id,
            }

        intent = session_result.working_state.intent_profile
        plan = self.runtime.evidence_planner.plan(intent)

        # 2. Retrieval & Packaging
        # We use the established CMK query pipeline
        if use_concepts and self.runtime.concept_retriever:
            pack = await self.runtime.query_with_concepts(
                user_query,
                top_k_concepts=self.runtime.config.retrieval.top_k_concepts,
                topic_filter=topic_filter,
                mission_filter=mission_filter,
            )
        else:
            pack = await self.runtime.query(
                user_query,
                topic_filter=topic_filter,
                mission_filter=mission_filter,
            )

        # Handle cross-document reasoning overlay
        reasoning_context = None
        if use_reasoning and self.distillation_pipeline:
            try:
                reasoning_context = await self.distillation_pipeline.query_with_reasoning(
                    user_query
                )
                if reasoning_context.get("supporting_beliefs"):
                    for sb in reasoning_context["supporting_beliefs"]:
                        pack.extra_context.append({
                            "claim": sb["claim"],
                            "confidence": sb["confidence"],
                            "source": "belief_graph",
                        })
                if reasoning_context.get("contradicting_beliefs"):
                    for cb in reasoning_context["contradicting_beliefs"]:
                        pack.extra_context.append({
                            "claim": cb["claim"],
                            "confidence": cb["confidence"],
                            "source": "belief_graph_contradiction",
                        })
            except Exception as e:
                logger.debug(f"[CMKChatBridge] Reasoning expansion failed: {e}")

        # Governor pre-generation checks
        atoms = pack.usable_atoms
        scores = [a.reliability for a in atoms]
        compressed, gov_decisions = self.governor.pre_generate(
            atoms, scores, user_query
        )

        # 3. Assemble backward-compatible result with new session fields
        return {
            "evidence_pack": pack,
            "intent": intent,
            "plan": plan,
            "working_brief": session_result.working_brief,
            "analysis_brief": session_result.analysis_brief,
            "analysis_result": session_result.analysis_result,
            "route": session_result.route,
            "compressed_context": compressed,
            "governor_decisions": gov_decisions,
            "reasoning_context": reasoning_context,
            "session_id": session_id
        }

    async def process_session_turn(
        self,
        user_query: str,
        session_id: str,
        mission_id: Optional[str] = None,
        topic_id: Optional[str] = None,
    ) -> SessionResult:
        """
        Additive session state update. Returns structured session guidance.
        Does NOT do retrieval; callers decide how to use the result.
        """
        if not self._initialized:
            await self.initialize()

        return await self.session_runtime.process_turn(
            session_id=session_id,
            user_text=user_query,
            agent_context={"mission_id": mission_id, "topic_id": topic_id}
        )

    async def extract_reasoning_overlay(self, user_query: str) -> Optional[Dict[str, Any]]:
        if not self.distillation_pipeline:
            return None
        try:
            return await self.distillation_pipeline.query_with_reasoning(user_query)
        except Exception as e:
            logger.debug(f"[CMKChatBridge] Reasoning overlay failed: {e}")
            return None

    @staticmethod
    def format_reasoning_overlay(reasoning_context: Optional[Dict[str, Any]]) -> str:
        if not reasoning_context:
            return ""

        sections: list[str] = []
        supporting = reasoning_context.get("supporting_beliefs") or []
        contradicting = reasoning_context.get("contradicting_beliefs") or []

        if supporting:
            sections.append("### Cross-Document Reasoning")
            for belief in supporting[:3]:
                claim = belief.get("claim") or ""
                confidence = belief.get("confidence")
                conf = f" ({confidence:.0%})" if isinstance(confidence, (int, float)) else ""
                if claim:
                    sections.append(f"- {claim}{conf}")

        if contradicting:
            if not sections:
                sections.append("### Cross-Document Reasoning")
            sections.append("Conflicting belief-graph signals:")
            for belief in contradicting[:2]:
                claim = belief.get("claim") or ""
                confidence = belief.get("confidence")
                conf = f" ({confidence:.0%})" if isinstance(confidence, (int, float)) else ""
                if claim:
                    sections.append(f"- {claim}{conf}")

        return "\n".join(sections)

    def record_feedback(
        self,
        result: Dict[str, Any],
        response_text: str,
        response_quality: float,
        response_id: str = "",
    ) -> Dict[str, Any]:
        pack = result["evidence_pack"]
        user_query = getattr(result.get("intent"), "_query", "")
        gov_decisions = self.governor.post_generate(response_text, user_query)
        if not pack:
            return {
                "governor_decisions": gov_decisions,
                "feedback_updates": {},
            }
        feedback = self.runtime.record_feedback(
            pack.usable_atoms, response_quality, response_id
        )
        return {
            "governor_decisions": gov_decisions,
            "feedback_updates": feedback,
        }
