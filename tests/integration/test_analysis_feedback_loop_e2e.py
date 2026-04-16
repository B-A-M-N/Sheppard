"""
Integration tests for Analysis Feedback Loop.
Verifies that AnalysisService correctly feeds applied reasoning back into authority records in real DB.
"""
import pytest
import asyncio
import uuid
import json
from unittest.mock import AsyncMock, MagicMock

from .test_knowledge_pipeline import adapter_real, FakeRedisClient, compute_hash
from src.research.reasoning.analysis_service import AnalysisService, AnalysisReport
from src.research.reasoning.assembler import EvidenceAssembler, EvidencePacket
from src.research.reasoning.v3_retriever import V3Retriever
from src.research.reasoning.problem_frame import ProblemFrame
from src.research.reasoning.analyst import AnalystOutput
from src.research.reasoning.adversarial_critic import CriticOutput
from src.llm.client import OllamaClient

def parse_json(val):
    if isinstance(val, str):
        return json.loads(val)
    return val

@pytest.mark.asyncio
async def test_analysis_feedback_loop_e2e(adapter_real):
    adapter = adapter_real
    suffix = uuid.uuid4().hex[:6]
    topic_id = f"t-anl-{suffix}"
    auth_id = f"dar-{suffix}"
    profile_id = f"p-{suffix}"
    
    # 1. Setup DB state
    await adapter.pg.insert_row("config.domain_profiles", {
        "profile_id": profile_id, "name": "T", "domain_type": "T", "description": "T", "config_json": "{}"
    })
    # MUST create mission to avoid FK violation in corpus.sources
    await adapter.pg.insert_row("mission.research_missions", {
        "mission_id": topic_id, "topic_id": topic_id, "domain_profile_id": profile_id, 
        "title": "Analysis Mission", "objective": "Test", "status": "active"
    })
    
    await adapter.pg.insert_row("authority.authority_records", {
        "authority_record_id": auth_id,
        "topic_id": topic_id,
        "domain_profile_id": profile_id,
        "title": "Existing Auth",
        "canonical_title": "Existing",
        "status_json": json.dumps({"maturity": "synthesized", "application_count": 0}),
        "advisory_layer_json": "{}",
        "reuse_json": "{}"
    })
    
    # Setup source and chunk for evidence requirement
    source_id = f"s-{suffix}"
    await adapter.pg.insert_row("corpus.sources", {
        "source_id": source_id, "mission_id": topic_id, "topic_id": topic_id,
        "url": "h", "normalized_url": "h", "normalized_url_hash": compute_hash(f"h-anl-{suffix}"),
        "source_class": "web", "status": "fetched"
    })
    chunk_id = f"c-{suffix}"
    await adapter.pg.insert_row("corpus.chunks", {
        "chunk_id": chunk_id, "source_id": source_id, "mission_id": topic_id, "topic_id": topic_id,
        "chunk_index": 0, "chunk_hash": compute_hash(f"E-anl-{suffix}"), "inline_text": "Fact content."
    })

    # Ingest an atom linked to this authority
    atom_id = f"a-{suffix}"
    await adapter.store_atom_with_evidence({
        "atom_id": atom_id, "topic_id": topic_id, "domain_profile_id": profile_id,
        "atom_type": "claim", "title": "A", "statement": "Technical fact.",
        "confidence": 1.0, "importance": 1.0, "novelty": 1.0,
        "authority_record_id": auth_id
    }, [{"source_id": source_id, "chunk_id": chunk_id, "evidence_strength": 1.0, "supports_statement": True}])
    
    await adapter.index_atom({
        "atom_id": atom_id, "topic_id": topic_id, "domain_profile_id": profile_id,
        "atom_type": "claim", "statement": "Technical fact.",
        "confidence": 1.0, "importance": 1.0, "novelty": 1.0, 
        "mission_id": topic_id, "authority_record_id": auth_id
    })
    await asyncio.sleep(0.3)

    # 2. Setup Service with Mocks for LLM stages
    mock_ollama = MagicMock(spec=OllamaClient)
    
    # Mock ProblemFramer
    mock_frame = ProblemFrame(
        raw_statement="How to fix X?",
        problem_type="troubleshooting",
        goal="Fix X",
        retrieval_queries=["fix X technical"]
    )
    
    # Mock Analyst
    mock_analyst = AnalystOutput(
        diagnosis="X is broken because of Y",
        confidence=0.85,
        recommendation="Apply patch Z",
        recommendation_rationale="Rationale Z",
        reasoning="Because...",
        risks=["Z might fail"],
        key_atoms=["[A1]"]
    )
    
    # Mock Critic
    mock_critic = CriticOutput(
        strongest_objection="Analyst missed W",
        overlooked_reasoning="W is important",
        counter_recommendation="Do V instead",
        overlooked_atoms=["[A1]"]
    )

    retriever = V3Retriever(adapter)
    assembler = EvidenceAssembler(mock_ollama, None, retriever, adapter)
    service = AnalysisService(mock_ollama, retriever, assembler)
    
    # Patch internal methods to return our mocks
    service.framer.frame = AsyncMock(return_value=mock_frame)
    service.analyst.analyze = AsyncMock(return_value=mock_analyst)
    service.critic.critique = AsyncMock(return_value=mock_critic)

    # 3. Run Analysis
    report = await service.analyze("How to fix X?", topic_filter=topic_id)

    # 4. Verify Application Tables
    aq_id = report.application_query_id
    aq_row = await adapter.pg.fetch_one("application.application_queries", {"application_query_id": aq_id})
    assert aq_row is not None
    
    outputs = await adapter.pg.fetch_many("application.application_outputs", {"application_query_id": aq_id})
    types = [o["output_type"] for o in outputs]
    assert "analysis_report" in types
    
    evidence = await adapter.pg.fetch_many("application.application_evidence", {"application_query_id": aq_id})
    assert len(evidence) >= 1

    # 5. Verify Feedback on Authority Record
    auth_row = await adapter.pg.fetch_one("authority.authority_records", {"authority_record_id": auth_id})
    
    status = parse_json(auth_row["status_json"])
    assert status["application_count"] >= 1
    
    advisory = parse_json(auth_row["advisory_layer_json"])
    assert advisory["application_feedback"]["last_recommendation"] == "Apply patch Z"
    assert "Z might fail" in advisory["risk_register"]
    
    reuse = parse_json(auth_row["reuse_json"])
    assert len(reuse["application_history"]) >= 1
    assert reuse["application_history"][-1]["recommendation"] == "Apply patch Z"
