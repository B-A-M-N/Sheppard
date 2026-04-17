from src.research.reasoning.problem_frame import ProblemFramer, RetrievalMode


def test_heuristic_frame_uses_deterministic_dimensions_and_temporal_mode():
    framer = ProblemFramer(ollama=None)
    frame = framer._heuristic_frame("What changed in the latest Postgres runtime behavior today?")
    assert frame.dimensions == ["mechanism", "tradeoffs", "constraints", "failure_modes", "implementation"]
    assert frame.retrieval_mode == RetrievalMode.TEMPORAL.value
    assert any("mechanism" in query for query in frame.retrieval_queries)


def test_follow_up_for_dimensions_builds_dimension_specific_queries():
    framer = ProblemFramer(ollama=None)
    frame = framer._heuristic_frame("How does the cache invalidation design work?")
    queries = framer.follow_up_for_dimensions(frame, ["failure_modes", "implementation"])
    assert any("failure modes" in query for query in queries)
    assert any("implementation" in query for query in queries)
