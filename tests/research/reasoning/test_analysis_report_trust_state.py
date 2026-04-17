from src.research.reasoning.analysis_service import AnalysisReport
from src.research.reasoning.problem_frame import ProblemFrame
from src.research.reasoning.analyst import AnalystOutput
from src.research.reasoning.adversarial_critic import CriticOutput


def _report(critic_objection: str, confidence: float = 0.8) -> AnalysisReport:
    return AnalysisReport(
        frame=ProblemFrame(raw_statement="Problem", retrieval_queries=["q"], problem_type="diagnostic"),
        analyst=AnalystOutput(
            diagnosis="Diagnosis",
            confidence=confidence,
            reasoning="Reasoning",
            recommendation="Recommendation",
            key_atoms=[],
        ),
        critic=CriticOutput(
            strongest_objection=critic_objection,
            overlooked_atoms=[],
        ),
        atom_count=4,
    )


def test_analysis_report_formats_trust_state():
    report = _report("Counter evidence exists.")

    formatted = report.formatted()

    assert "TRUST STATE: CONTESTED" in formatted


def test_analysis_report_reusable_without_critic_objection():
    report = _report("", confidence=0.85)

    assert report.trust_state == "reusable"


def test_analysis_report_formats_list_reasoning_without_crashing():
    report = AnalysisReport(
        frame=ProblemFrame(raw_statement="Problem", retrieval_queries=["q"], problem_type="diagnostic"),
        analyst=AnalystOutput(
            diagnosis="Diagnosis",
            confidence=0.8,
            reasoning=["First reason", "Second reason"],
            recommendation="Recommendation",
            key_atoms=[],
        ),
        critic=CriticOutput(
            strongest_objection="Counter evidence exists.",
            overlooked_atoms=[],
        ),
        atom_count=4,
    )

    formatted = report.formatted()

    assert "First reason" in formatted
    assert "Second reason" in formatted
    assert "DIAGNOSIS  [80% confidence]" in formatted
