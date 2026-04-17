from src.research.reasoning.trust_state import derive_trust_state


def test_derive_trust_state_prefers_stale():
    assert derive_trust_state({"freshness": "stale", "maturity": "synthesized"}, {}, {}) == "stale"


def test_derive_trust_state_marks_contested_from_critic_signal():
    assert derive_trust_state(
        {"maturity": "synthesized"},
        {"critic_objections": ["Evidence pushes the other way."]},
        {},
    ) == "contested"


def test_derive_trust_state_marks_reusable_after_successful_application():
    assert derive_trust_state(
        {"maturity": "synthesized", "successful_application_count": 2},
        {},
        {"application_history": [{"application_query_id": "aq-1"}]},
    ) == "reusable"
