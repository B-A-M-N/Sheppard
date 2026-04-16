"""
Integration tests for Authority Maturation Flow.
Verifies that SynthesisService correctly promotes authority records in real DB.
"""
import pytest
import asyncio
import uuid
import json
from unittest.mock import AsyncMock, MagicMock, patch

from .test_knowledge_pipeline import adapter_real, FakeRedisClient, compute_hash
from src.research.reasoning.synthesis_service import SynthesisService
from src.research.reasoning.assembler import EvidenceAssembler, EvidencePacket, SectionPlan
from src.research.reasoning.v3_retriever import V3Retriever
from src.llm.client import OllamaClient

def parse_json(val):
    if isinstance(val, str):
        return json.loads(val)
    return val

@pytest.mark.asyncio
async def test_authority_maturation_e2e(adapter_real):
    adapter = adapter_real
    suffix = uuid.uuid4().hex[:6]
    mission_id = f"m-mat-{suffix}"
    profile_id = f"p-mat-{suffix}"
    
    # 1. Setup DB state
    await adapter.pg.insert_row("config.domain_profiles", {
        "profile_id": profile_id, "name": "T", "domain_type": "T", "description": "T", "config_json": "{}"
    })
    await adapter.pg.insert_row("mission.research_missions", {
        "mission_id": mission_id, "topic_id": mission_id, "domain_profile_id": profile_id, 
        "title": "Maturity Mission", "objective": "Test", "status": "active"
    })
    
    # Create contradiction set to avoid FK violation
    contradiction_set_id = f"cset-{suffix}"
    await adapter.pg.insert_row("knowledge.contradiction_sets", {
        "contradiction_set_id": contradiction_set_id,
        "topic_id": mission_id,
        "summary": "Conflict A vs B",
        "resolution_status": "unresolved"
    })
    
    # Ingest source and atoms
    source_id = f"s-{suffix}"
    await adapter.pg.insert_row("corpus.sources", {
        "source_id": source_id, "mission_id": mission_id, "topic_id": mission_id,
        "url": "h", "normalized_url": "h", "normalized_url_hash": compute_hash(f"h-{suffix}"),
        "source_class": "web", "status": "fetched"
    })
    chunk_id = f"c-{suffix}"
    await adapter.pg.insert_row("corpus.chunks", {
        "chunk_id": chunk_id, "source_id": source_id, "mission_id": mission_id, "topic_id": mission_id,
        "chunk_index": 0, "chunk_hash": compute_hash(f"E-{suffix}"), "inline_text": "Evidence for maturation."
    })

    atom_ids = [f"a-{suffix}-{i}" for i in range(3)]
    for i, aid in enumerate(atom_ids):
        await adapter.store_atom_with_evidence({
            "atom_id": aid, "topic_id": mission_id, "domain_profile_id": profile_id,
            "atom_type": "claim", "title": f"A{i}", "statement": f"Maturation evidence {i}.",
            "confidence": 1.0, "importance": 1.0, "novelty": 1.0
        }, [{"source_id": source_id, "chunk_id": chunk_id, "evidence_strength": 1.0, "supports_statement": True}])
        # Index for retriever
        await adapter.index_atom({
            "atom_id": aid, "topic_id": mission_id, "domain_profile_id": profile_id,
            "atom_type": "claim", "statement": f"Maturation evidence {i}.",
            "confidence": 1.0, "importance": 1.0, "novelty": 1.0, "mission_id": mission_id
        })
    
    await asyncio.sleep(0.3)

    # 2. Setup Service
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_ollama.complete = AsyncMock(return_value="Maturation evidence 0 [A1]. Maturation evidence 1 [A2]. Maturation evidence 2 [A3].")
    mock_ollama.embed = AsyncMock(return_value=[0.1] * 768)

    retriever = V3Retriever(adapter)
    assembler = EvidenceAssembler(mock_ollama, None, retriever, adapter)
    
    # We want one successful section and one insufficient section to test advisory logic
    assembler.generate_section_plan = AsyncMock(return_value=[
        SectionPlan(order=1, title="Success", purpose="P1", target_evidence_roles=["contradictions"]),
        SectionPlan(order=2, title="Gap", purpose="P2", target_evidence_roles=[])
    ])
    
    original_assemble = assembler.assemble_all_sections
    async def patched_assemble(mid, tname, plan):
        packets = await original_assemble(mid, tname, plan)
        # Force section 2 to be empty
        if 2 in packets:
            packets[2].atoms = []
            packets[2].atom_ids_used = []
        # Inject global_ids for section 1
        if 1 in packets:
            for i, atom in enumerate(packets[1].atoms):
                atom['global_id'] = f"A{i+1}"
        return packets
    assembler.assemble_all_sections = patched_assemble

    # Inject a contradiction to test advisory maturation
    with patch.object(EvidenceAssembler, '_get_unresolved_contradictions', AsyncMock(return_value=[
        {"description": "Conflict A vs B", "atom_a_content": "A", "atom_b_content": "B", "contradiction_set_id": contradiction_set_id}
    ])):
        service = SynthesisService(mock_ollama, None, assembler, adapter)
        await service.generate_master_brief(mission_id)

    # 3. Verify Authority Record promotion
    auth_id = f"dar_{mission_id[:8]}"
    row = await adapter.pg.fetch_one("authority.authority_records", {"authority_record_id": auth_id})
    assert row is not None
    
    status = parse_json(row["status_json"])
    assert status["maturity"] == "contested" # because of contradiction
    assert status["advisory_count"] >= 2 # 1 contradiction + 1 coverage gap
    assert status["section_count"] == 2
    
    advisory = parse_json(row["advisory_layer_json"])
    assert "Conflict A vs B" in advisory["major_contradictions"]
    assert "Gap" in advisory["coverage_gaps"]
    
    reuse = parse_json(row["reuse_json"])
    assert reuse["reusable_section_count"] == 1
    assert len(reuse["artifact_ids"]) == 1
    
    # 4. Verify Side Tables
    advisories = await adapter.pg.fetch_many("authority.authority_advisories", {"authority_record_id": auth_id})
    types = [a["advisory_type"] for a in advisories]
    assert "contradiction_risk" in types
    assert "coverage_gap" in types
