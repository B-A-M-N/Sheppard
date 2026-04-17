import pytest

from src.core.memory.cmk.escalation_policy import EscalationPolicy
from src.core.memory.cmk.intent_profiler import IntentProfiler
from src.core.memory.cmk.session_runtime import CognitiveSessionRuntime
from src.core.memory.cmk.state_store import WorkingStateStore


class InMemoryStateStore(WorkingStateStore):
    def __init__(self):
        self._states = {}

    async def load(self, session_id):
        return self._states.get(session_id)

    async def save(self, state, ttl=0):
        self._states[state.session_id] = state
        return True


class FakeItem:
    def __init__(self, content, citation_key=None, metadata=None, relevance_score=0.6, trust_score=0.7):
        self.content = content
        self.citation_key = citation_key
        self.metadata = metadata or {}
        self.relevance_score = relevance_score
        self.trust_score = trust_score


class FakeContext:
    def __init__(self):
        self.evidence = [
            FakeItem(
                "Redis queue depth increased",
                metadata={"atom_id": "a1", "title": "Redis queue", "contradicts": ["a2"]},
            ),
            FakeItem(
                "Redis queue depth did not increase",
                metadata={"atom_id": "a2", "title": "Worker contention", "contradicts": ["a1"]},
            ),
        ]
        self.contradictions = [
            FakeItem(
                "Unresolved contradiction: queue is healthy VS queue is saturated",
                citation_key="cx-1",
                metadata={"contradiction_set_id": "cx-1", "atom_a_id": "a1", "atom_b_id": "a3"},
            )
        ]
        self.unresolved = [
            FakeItem("Need to explain why throughput drops after deploy", citation_key="u-1", metadata={"atom_id": "a4"})
        ]
        self.project_artifacts = [
            FakeItem("scheduler.py may contain relevant implementation evidence", citation_key="artifact-1", metadata={"atom_id": "a5", "title": "scheduler.py"})
        ]
        self.definitions = [
            FakeItem("Authority summary", citation_key="auth-1", metadata={"canonical_title": "Queue handling"})
        ]
        self.aggregate_trust_state = "contested"


class FakeRetriever:
    async def retrieve(self, query):
        return FakeContext()


class FakeRuntime:
    def __init__(self):
        self.recorded_steps = []
        self.contradiction_detector = type(
            "Detector",
            (),
            {
                "detect": staticmethod(
                    lambda atoms, similarity_threshold=0.6: [
                        {"atom_a": "a1", "atom_b": "a2", "description": "Derived contradiction", "type": "explicit"}
                    ]
                )
            },
        )()

    def identify_blind_spots(self):
        return [{"type": "calibration_error", "severity": 0.8}]

    def get_blind_spots(self):
        return self.identify_blind_spots()

    def generate_research_agenda(self, top_k=2):
        return [
            {"description": "Test relational gap", "reason": "Missing bridge between queue and worker saturation", "priority": 0.7}
        ]

    def record_reasoning_step(self, step_type, input_data, output_data, confidence):
        self.recorded_steps.append((step_type, input_data, output_data, confidence))


@pytest.mark.asyncio
async def test_session_runtime_populates_state_from_existing_signals():
    fake_runtime = FakeRuntime()
    runtime = CognitiveSessionRuntime(
        state_store=InMemoryStateStore(),
        intent_profiler=IntentProfiler(),
        retriever=FakeRetriever(),
        belief_graph=None,
        escalation_policy=EscalationPolicy(),
        analysis_service=None,
        cmk_runtime=fake_runtime,
    )

    result = await runtime.process_turn(
        session_id="s1",
        user_text="compare redis queue behavior after deploy",
        agent_context={"mission_id": "mission-1", "topic_id": "topic-1"},
    )

    state = result.working_state
    assert result.route == "chat"
    assert state.active_atom_ids == ["a1", "a2"]
    assert state.active_derived_claim_ids == ["auth-1"]
    assert state.active_contradictions
    assert state.active_contradictions[0].contradiction_id == "cx-1"
    assert any(contradiction.summary == "Derived contradiction" for contradiction in state.active_contradictions)
    assert state.soft_hypotheses
    assert any("throughput drops after deploy" in hypothesis.text for hypothesis in state.soft_hypotheses)
    assert state.confidence_pressure > 0.5
    assert state.insufficiency_pressure > 0.2
    assert "SALIENT CONCEPTS" in (result.working_brief or "")
    assert fake_runtime.recorded_steps
    assert fake_runtime.recorded_steps[0][0] == "retrieval"
