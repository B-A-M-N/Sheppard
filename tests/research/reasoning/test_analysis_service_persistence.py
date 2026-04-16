import pytest

from src.research.reasoning.analysis_service import AnalysisService
from src.research.reasoning.problem_frame import ProblemFrame
from src.research.reasoning.analyst import AnalystOutput
from src.research.reasoning.adversarial_critic import CriticOutput
from src.research.reasoning.assembler import EvidencePacket


class RecordingAdapter:
    def __init__(self):
        self.queries = []
        self.outputs = []
        self.lineage = []
        self.evidence = []
        self.authority_updates = []
        self.authority_records = {
            "auth-1": {
                "authority_record_id": "auth-1",
                "topic_id": "mission-1",
                "domain_profile_id": "profile-1",
                "title": "Authority One",
                "canonical_title": "Authority One",
                "scope_json": {},
                "frontier_summary_json": {},
                "corpus_layer_json": {},
                "atom_layer_json": {},
                "synthesis_layer_json": {},
                "lineage_layer_json": {},
                "status_json": {"maturity": "synthesized", "application_count": 2, "authority_score": 0.4},
                "advisory_layer_json": {"decision_rules": ["Existing rule"]},
                "reuse_json": {"application_history": []},
            }
        }

    async def create_application_query(self, query):
        self.queries.append(query)

    async def store_application_output(self, output):
        self.outputs.append(output)

    async def store_application_lineage(self, application_query_id, lineage_json):
        self.lineage.append((application_query_id, lineage_json))

    async def bind_application_evidence(self, application_query_id, rows):
        self.evidence.append((application_query_id, rows))

    async def get_authority_record(self, authority_record_id):
        return self.authority_records.get(authority_record_id)

    async def upsert_authority_record(self, row):
        self.authority_updates.append(row)


class StubAssembler:
    def __init__(self, adapter):
        self.adapter = adapter


@pytest.mark.asyncio
async def test_persist_application_run_records_query_output_and_evidence():
    adapter = RecordingAdapter()
    service = AnalysisService(ollama=None, retriever=None, assembler=StubAssembler(adapter))

    report = type("Report", (), {})()
    report.frame = ProblemFrame(
        raw_statement="Why is latency spiking?",
        goal="Reduce latency spikes",
        symptoms=["p99 latency doubled"],
        constraints=["No hardware changes"],
        domain_hints=["networking"],
        retrieval_queries=["latency spike causes"],
        problem_type="diagnostic",
    )
    report.analyst = AnalystOutput(
        diagnosis="Queue contention.",
        confidence=0.82,
        reasoning="Reasoning",
        recommendation="Reduce contention",
        recommendation_rationale="The queue hotspot dominates the evidence.",
        risks=["Could increase tail latency during bursts."],
        open_questions=["Do spikes correlate with deployment windows?"],
        key_atoms=["[A1]"],
    )
    report.critic = CriticOutput(
        strongest_objection="Could also be packet loss.",
        overlooked_atoms=["[A2]"],
        overlooked_reasoning="The packet-loss evidence was underweighted.",
        counter_recommendation="Measure drops first.",
        confidence_assessment="Slightly too high.",
    )
    report.atom_count = 2
    report.mission_filter = "mission-1"
    report.application_query_id = None
    report.formatted = lambda: "full analysis text"

    packet = EvidencePacket(
        topic_name="topic",
        section_title="analysis",
        section_objective="objective",
        atoms=[
            {"global_id": "[A1]", "metadata": {"atom_id": "atom-1", "authority_record_id": "auth-1"}},
            {"global_id": "[A1]", "metadata": {"atom_id": "atom-1", "authority_record_id": "auth-1"}},
            {"global_id": "[A2]", "metadata": {"atom_id": "atom-2"}},
        ],
        contradictions=[{"description": "conflict"}],
    )

    await service._persist_application_run(
        problem_statement="Why is latency spiking?",
        mission_filter="mission-1",
        topic_filter=None,
        report=report,
        packet=packet,
    )

    assert len(adapter.queries) == 1
    assert adapter.queries[0]["query_type"] == "analysis"
    assert adapter.queries[0]["project_id"] == "mission-1"
    assert adapter.outputs[0]["output_type"] == "analysis_report"
    assert adapter.outputs[0]["inline_text"] == "full analysis text"
    assert [output["output_type"] for output in adapter.outputs] == [
        "analysis_report",
        "analysis_risk_register",
        "critic_challenge",
        "analysis_open_questions",
    ]
    assert len(adapter.evidence) == 1
    application_query_id, rows = adapter.evidence[0]
    assert application_query_id == report.application_query_id
    assert adapter.lineage[0][0] == report.application_query_id
    assert adapter.lineage[0][1]["frame"]["problem_type"] == "diagnostic"
    assert adapter.lineage[0][1]["critic"]["counter_recommendation"] == "Measure drops first."
    assert len(adapter.authority_updates) == 1
    authority_update = adapter.authority_updates[0]
    assert authority_update["authority_record_id"] == "auth-1"
    assert authority_update["topic_id"] == "mission-1"
    assert authority_update["domain_profile_id"] == "profile-1"
    assert authority_update["title"] == "Authority One"
    assert authority_update["canonical_title"] == "Authority One"
    assert authority_update["status_json"]["application_count"] == 3
    assert authority_update["status_json"]["successful_application_count"] == 1
    assert authority_update["status_json"]["authority_score"] > 0.4
    assert authority_update["status_json"]["has_critic_review"] is True
    assert authority_update["advisory_layer_json"]["application_feedback"]["last_application_query_id"] == report.application_query_id
    assert authority_update["advisory_layer_json"]["risk_register"] == ["Could increase tail latency during bursts."]
    assert authority_update["advisory_layer_json"]["critic_objections"] == ["Could also be packet loss."]
    assert authority_update["reuse_json"]["last_application_query_id"] == report.application_query_id
    assert authority_update["reuse_json"]["key_atom_ids"] == ["atom-1"]
    assert authority_update["reuse_json"]["critic_overlooked_atom_ids"] == ["atom-2"]
    assert rows == [
        {"authority_record_id": "auth-1", "atom_id": "atom-1", "bundle_id": None},
        {"authority_record_id": None, "atom_id": "atom-2", "bundle_id": None},
    ]


@pytest.mark.asyncio
async def test_multi_query_retrieve_uses_topic_filter_for_contradictions():
    adapter = RecordingAdapter()
    assembler = StubAssembler(adapter)
    assembler._get_unresolved_contradictions_calls = []

    async def _get_unresolved_contradictions(scope, limit=8):
        assembler._get_unresolved_contradictions_calls.append((scope, limit))
        return [{"description": "conflict", "atom_a_content": "A", "atom_b_content": "B"}]

    assembler._get_unresolved_contradictions = _get_unresolved_contradictions

    class FakeRetriever:
        async def retrieve(self, query):
            item = type(
                "Item",
                (),
                {
                    "citation_key": "[A1]",
                    "content": "Atom text",
                    "item_type": "claim",
                    "trust_score": 0.8,
                    "metadata": {"atom_id": "atom-1"},
                },
            )()
            return type("Ctx", (), {"all_items": [item]})()

    service = AnalysisService(ollama=None, retriever=FakeRetriever(), assembler=assembler)
    frame = ProblemFrame(
        raw_statement="question",
        retrieval_queries=["question"],
        problem_type="diagnostic",
    )

    packet = await service._multi_query_retrieve(
        frame=frame,
        mission_filter=None,
        topic_filter="topic-9",
    )

    assert assembler._get_unresolved_contradictions_calls == [("topic-9", 8)]
    assert packet.contradictions == [{"description": "conflict", "claim_a": "A", "claim_b": "B"}]
