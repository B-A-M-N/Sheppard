import json
import uuid
from unittest.mock import MagicMock

import pytest

from .test_knowledge_pipeline import adapter_real, compute_hash
from src.llm.client import OllamaClient
from src.research.reasoning.adversarial_critic import CriticOutput
from src.research.reasoning.analysis_service import AnalysisReport, AnalysisService
from src.research.reasoning.analyst import AnalystOutput
from src.research.reasoning.assembler import EvidenceAssembler, EvidencePacket
from src.research.reasoning.problem_frame import ProblemFrame
from src.research.reasoning.v3_retriever import V3Retriever


def parse_json(val):
    if isinstance(val, str):
        return json.loads(val)
    return val


@pytest.mark.asyncio
async def test_analysis_application_e2e(adapter_real):
    adapter = adapter_real
    suffix = uuid.uuid4().hex[:6]
    topic_id = f"topic-app-{suffix}"
    profile_id = f"profile-app-{suffix}"
    authority_record_id = f"dar-app-{suffix}"

    await adapter.pg.insert_row("config.domain_profiles", {
        "profile_id": profile_id, "name": "Application", "domain_type": "technical", "description": "Analysis e2e", "config_json": "{}"
    })
    await adapter.pg.insert_row("mission.research_missions", {
        "mission_id": topic_id, "topic_id": topic_id, "domain_profile_id": profile_id,
        "title": "Analysis Mission", "objective": "Validate application persistence", "status": "active"
    })
    await adapter.upsert_authority_record({
        "authority_record_id": authority_record_id,
        "topic_id": topic_id,
        "domain_profile_id": profile_id,
        "title": "Latency Authority",
        "canonical_title": "Latency Authority",
        "status_json": {"maturity": "synthesized", "application_count": 2},
        "advisory_layer_json": {"decision_rules": ["Existing rule"]},
        "reuse_json": {"application_history": []},
    })

    source_id = f"src-app-{suffix}"
    chunk_id = f"chk-app-{suffix}"
    url = f"https://example.com/application/{suffix}"
    await adapter.pg.insert_row("corpus.sources", {
        "source_id": source_id, "mission_id": topic_id, "topic_id": topic_id,
        "url": url, "normalized_url": url, "normalized_url_hash": compute_hash(url),
        "source_class": "web", "status": "fetched"
    })
    await adapter.pg.insert_row("corpus.chunks", {
        "chunk_id": chunk_id, "source_id": source_id, "mission_id": topic_id, "topic_id": topic_id,
        "chunk_index": 0, "chunk_hash": compute_hash(f"application-{suffix}"),
        "inline_text": "Queue contention produces latency spikes during bursts."
    })

    atom_ids = [f"atom-app-{suffix}-1", f"atom-app-{suffix}-2"]
    await adapter.store_atom_with_evidence({
        "atom_id": atom_ids[0],
        "mission_id": topic_id,
        "topic_id": topic_id,
        "domain_profile_id": profile_id,
        "authority_record_id": authority_record_id,
        "atom_type": "claim",
        "title": "Primary Atom",
        "statement": "Queue contention produces latency spikes during bursts.",
        "confidence": 0.93,
        "importance": 0.9,
        "novelty": 0.4,
    }, [{
        "source_id": source_id,
        "chunk_id": chunk_id,
        "evidence_strength": 1.0,
        "supports_statement": True,
    }])
    await adapter.store_atom_with_evidence({
        "atom_id": atom_ids[1],
        "mission_id": topic_id,
        "topic_id": topic_id,
        "domain_profile_id": profile_id,
        "atom_type": "claim",
        "title": "Secondary Atom",
        "statement": "Packet loss can mimic the same symptom profile.",
        "confidence": 0.8,
        "importance": 0.5,
        "novelty": 0.4,
    }, [{
        "source_id": source_id,
        "chunk_id": chunk_id,
        "evidence_strength": 0.8,
        "supports_statement": True,
    }])

    mock_ollama = MagicMock(spec=OllamaClient)
    retriever = V3Retriever(adapter)
    assembler = EvidenceAssembler(mock_ollama, None, retriever, adapter)
    service = AnalysisService(mock_ollama, retriever, assembler)

    report = AnalysisReport(
        frame=ProblemFrame(
            raw_statement="Why is latency spiking?",
            goal="Reduce latency spikes",
            symptoms=["p99 latency doubled"],
            constraints=["No hardware changes"],
            domain_hints=["networking"],
            retrieval_queries=["latency spike queue contention"],
            problem_type="diagnostic",
        ),
        analyst=AnalystOutput(
            diagnosis="Queue contention is the primary bottleneck.",
            confidence=0.84,
            reasoning="The latency pattern aligns with queue saturation under burst traffic.",
            recommendation="Reduce contention at the shared queue.",
            recommendation_rationale="The queue hotspot dominates the retrieved evidence.",
            risks=["Changes may increase tail latency during rebalancing."],
            open_questions=["Do spikes correlate with deploy windows?"],
            key_atoms=["[A1]"],
        ),
        critic=CriticOutput(
            strongest_objection="Packet loss was underweighted.",
            overlooked_atoms=["[A2]"],
            overlooked_reasoning="Loss can present the same symptoms before queue saturation is visible.",
            counter_recommendation="Measure packet drops before shipping the queue change.",
            confidence_assessment="Confidence is slightly too high.",
        ),
        atom_count=2,
    )
    packet = EvidencePacket(
        topic_name=topic_id,
        section_title="analysis",
        section_objective="Persist application feedback",
        atoms=[
            {"global_id": "[A1]", "metadata": {"atom_id": atom_ids[0], "authority_record_id": authority_record_id}},
            {"global_id": "[A1]", "metadata": {"atom_id": atom_ids[0], "authority_record_id": authority_record_id}},
            {"global_id": "[A2]", "metadata": {"atom_id": atom_ids[1]}},
        ],
        contradictions=[{"description": "Queue contention vs packet loss"}],
        section_guidance=[{"title": "Latency", "mode": "adjudicative"}],
        evidence_graph=type(
            "Graph",
            (),
            {
                "nodes": {
                    "n1": type("Node", (), {"node_type": "evidence"})(),
                    "n2": type("Node", (), {"node_type": "contradiction"})(),
                },
                "edges": {"e1": object()},
            },
        )(),
    )

    await service._persist_application_run(
        problem_statement="Why is latency spiking?",
        mission_filter=None,
        topic_filter=topic_id,
        report=report,
        packet=packet,
    )

    application_query_id = report.application_query_id
    query_row = await adapter.pg.fetch_one("application.application_queries", {"application_query_id": application_query_id})
    assert query_row["project_id"] == topic_id
    payload = parse_json(query_row["payload_json"])
    assert payload["problem_type"] == "diagnostic"
    assert payload["atom_count"] == 3
    assert payload["critic_overlooked_atoms"] == ["[A2]"]
    assert payload["graph_summary"]["guidance_count"] == 1
    assert payload["graph_summary"]["contradiction_nodes"] == 1

    outputs = await adapter.pg.fetch_many(
        "application.application_outputs",
        {"application_query_id": application_query_id},
        order_by="output_id ASC",
    )
    assert [output["output_type"] for output in outputs] == [
        "analysis_report",
        "analysis_risk_register",
        "critic_challenge",
        "analysis_graph_summary",
        "analysis_open_questions",
    ]

    lineage_row = await adapter.pg.fetch_one(
        "application.application_lineage",
        {"application_query_id": application_query_id},
    )
    lineage = parse_json(lineage_row["lineage_json"])
    assert lineage["frame"]["goal"] == "Reduce latency spikes"
    assert lineage["critic"]["counter_recommendation"] == "Measure packet drops before shipping the queue change."
    assert lineage["graph_summary"]["guidance_count"] == 1

    evidence_rows = await adapter.pg.fetch_many(
        "application.application_evidence",
        {"application_query_id": application_query_id},
        order_by="evidence_id ASC",
    )
    assert len(evidence_rows) == 2
    assert evidence_rows[0]["authority_record_id"] == authority_record_id
    assert evidence_rows[0]["atom_id"] == atom_ids[0]
    assert evidence_rows[0]["bundle_id"] is None
    assert evidence_rows[1]["authority_record_id"] is None
    assert evidence_rows[1]["atom_id"] == atom_ids[1]
    assert evidence_rows[1]["bundle_id"] is None

    authority_row = await adapter.pg.fetch_one("authority.authority_records", {"authority_record_id": authority_record_id})
    status = parse_json(authority_row["status_json"])
    advisory = parse_json(authority_row["advisory_layer_json"])
    reuse = parse_json(authority_row["reuse_json"])

    assert status["application_count"] == 3
    assert status["successful_application_count"] == 1
    assert status["authority_score"] > 0
    assert status["has_critic_review"] is True
    assert status["trust_state"] == "contested"
    assert status["last_application_query_id"] == application_query_id
    assert advisory["application_feedback"]["last_application_query_id"] == application_query_id
    assert advisory["application_feedback"]["last_recommendation"] == "Reduce contention at the shared queue."
    assert advisory["risk_register"] == ["Changes may increase tail latency during rebalancing."]
    assert advisory["critic_objections"] == ["Packet loss was underweighted."]
    assert reuse["last_application_query_id"] == application_query_id
    assert reuse["key_atom_ids"] == [atom_ids[0]]
    assert reuse["critic_overlooked_atom_ids"] == [atom_ids[1]]
    assert reuse["application_history"][-1]["recommendation"] == "Reduce contention at the shared queue."
