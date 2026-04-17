from src.core.memory.cmk.escalation_policy import EscalationPolicy
from src.core.memory.cmk.intent_profiler import IntentProfiler
from src.core.memory.cmk.working_state import WorkingState


def test_procedural_query_stays_on_chat_path():
    profiler = IntentProfiler()
    policy = EscalationPolicy()
    state = WorkingState(session_id="s1")
    state.intent_profile = profiler.profile("how to install redis on ubuntu")

    decision = policy.decide(state, "how to install redis on ubuntu")

    assert decision.route == "chat"
    assert decision.level == "medium"


def test_explicit_diagnosis_request_routes_to_analysis():
    profiler = IntentProfiler()
    policy = EscalationPolicy()
    state = WorkingState(session_id="s2")
    state.intent_profile = profiler.profile("diagnose the latency issue and recommend a fix")

    decision = policy.decide(state, "diagnose the latency issue and recommend a fix")

    assert decision.route == "analysis"
    assert decision.level == "full_analysis"
