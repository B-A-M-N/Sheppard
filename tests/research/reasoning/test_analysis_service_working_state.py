import pytest

from src.research.reasoning.analysis_service import AnalysisService
from src.research.reasoning.problem_frame import ProblemFrame
from src.core.memory.cmk.intent_profiler import IntentProfile
from src.core.memory.cmk.working_state import WorkingState


class StubAssembler:
    adapter = None


@pytest.mark.asyncio
async def test_run_from_working_state_uses_session_scope_and_candidate_frames():
    service = AnalysisService(ollama=None, retriever=None, assembler=StubAssembler())

    frame = ProblemFrame(
        raw_statement="why is throughput low",
        domain_hints=["networking"],
        retrieval_queries=["throughput bottleneck"],
    )

    async def fake_frame(user_text):
        return frame

    retrieve_calls = []
    persist_calls = []

    async def fake_retrieve(frame, mission_filter=None, topic_filter=None):
        retrieve_calls.append((mission_filter, topic_filter, sorted(frame.domain_hints)))
        return type("Packet", (), {"atoms": [{"id": "a1"}]})()

    async def fake_persist(problem_statement, mission_filter, topic_filter, report, packet):
        persist_calls.append((problem_statement, mission_filter, topic_filter, report.frame.domain_hints))

    async def fake_analyze(packet, frame):
        return type(
            "AnalystOutput",
            (),
            {"diagnosis": "Queueing", "recommendation": "Reduce queue depth", "confidence": 0.81},
        )()

    async def fake_critique(analyst_output, packet):
        return type(
            "CriticOutput",
            (),
            {"strongest_objection": "Could be packet loss", "counter_recommendation": "Measure drops first"},
        )()

    service.framer.frame = fake_frame
    service._multi_query_retrieve = fake_retrieve
    service._persist_application_run = fake_persist
    service.analyst.analyze = fake_analyze
    service.critic.critique = fake_critique

    state = WorkingState(
        session_id="session-1",
        mission_id="mission-7",
        topic_id="topic-2",
        candidate_frames=["comparison"],
        intent_profile=IntentProfile(
            type="comparative",
            depth="deep",
            stability="static",
            risk_of_hallucination=0.4,
            candidate_frames=["tradeoff_evaluation"],
        ),
    )

    result = await service.run_from_working_state("compare two queue strategies", state)

    assert retrieve_calls == [("mission-7", "topic-2", sorted(["networking", "comparison", "tradeoff_evaluation"]))]
    assert persist_calls == [
        (
            "compare two queue strategies",
            "mission-7",
            "topic-2",
            ["networking", "comparison", "tradeoff_evaluation"],
        )
    ]
    assert result["diagnosis"] == "Queueing"
    assert result["trust_state"] == "contested"
