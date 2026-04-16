import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from .test_knowledge_pipeline import adapter_real, compute_hash
from src.llm.client import OllamaClient
from src.research.reasoning.assembler import EvidenceAssembler, EvidencePacket, SectionPlan
from src.research.reasoning.synthesis_service import SynthesisService
from src.research.reasoning.v3_retriever import V3Retriever


def parse_json(val):
    if isinstance(val, str):
        return json.loads(val)
    return val


@pytest.mark.asyncio
async def test_authority_pipeline_e2e(adapter_real):
    adapter = adapter_real
    suffix = uuid.uuid4().hex[:6]
    mission_id = f"m-auth-{suffix}"
    profile_id = f"p-auth-{suffix}"
    related_auth_id = f"dar-related-{suffix}"
    contradiction_set_id = f"contra-{suffix}"

    await adapter.pg.insert_row("config.domain_profiles", {
        "profile_id": profile_id, "name": "Authority", "domain_type": "technical", "description": "Authority e2e", "config_json": "{}"
    })
    await adapter.pg.insert_row("mission.research_missions", {
        "mission_id": mission_id, "topic_id": mission_id, "domain_profile_id": profile_id,
        "title": "Authority Mission", "objective": "Validate authority binding", "status": "active"
    })
    await adapter.upsert_authority_record({
        "authority_record_id": related_auth_id,
        "topic_id": mission_id,
        "domain_profile_id": profile_id,
        "title": "Related Authority",
        "canonical_title": "Related Authority",
        "status_json": {"maturity": "forming"},
    })

    source_id = f"src-{suffix}"
    chunk_id = f"chk-{suffix}"
    url = f"https://example.com/authority/{suffix}"
    await adapter.pg.insert_row("corpus.sources", {
        "source_id": source_id, "mission_id": mission_id, "topic_id": mission_id,
        "url": url, "normalized_url": url, "normalized_url_hash": compute_hash(url),
        "source_class": "web", "status": "fetched"
    })
    await adapter.pg.insert_row("corpus.chunks", {
        "chunk_id": chunk_id, "source_id": source_id, "mission_id": mission_id, "topic_id": mission_id,
        "chunk_index": 0, "chunk_hash": compute_hash(f"authority-{suffix}"),
        "inline_text": "Feature flags must be evaluated against rollout safety and rollback speed."
    })

    atom_ids = [f"atom-{suffix}-{idx}" for idx in range(3)]
    for idx, atom_id in enumerate(atom_ids):
        await adapter.store_atom_with_evidence({
            "atom_id": atom_id,
            "mission_id": mission_id,
            "topic_id": mission_id,
            "domain_profile_id": profile_id,
            "atom_type": "claim",
            "title": f"Authority Atom {idx + 1}",
            "statement": f"Feature flag evidence {idx + 1} for staged rollout safety.",
            "confidence": 0.9,
            "importance": 0.8,
            "novelty": 0.5,
        }, [{
            "source_id": source_id,
            "chunk_id": chunk_id,
            "evidence_strength": 1.0,
            "supports_statement": True,
        }])

    await adapter.create_contradiction_set({
        "contradiction_set_id": contradiction_set_id,
        "topic_id": mission_id,
        "authority_record_id": related_auth_id,
        "summary": "Rollout policy conflicts on when to disable the flag.",
        "resolution_status": "unresolved",
    })
    await adapter.add_contradiction_members(contradiction_set_id, [
        {"atom_id": atom_ids[0], "position_label": "claim_a"},
        {"atom_id": atom_ids[1], "position_label": "claim_b"},
    ])

    mock_ollama = MagicMock(spec=OllamaClient)
    mock_ollama.complete = AsyncMock(return_value=(
        "Feature flag evidence 1 for staged rollout safety [A1]. "
        "Feature flag evidence 2 for staged rollout safety [A2]. "
        "Feature flag evidence 3 for staged rollout safety [A3]."
    ))
    mock_ollama.embed = AsyncMock(return_value=[0.1] * 768)

    retriever = V3Retriever(adapter)
    assembler = EvidenceAssembler(mock_ollama, None, retriever, adapter)
    assembler.generate_section_plan = AsyncMock(return_value=[
        SectionPlan(order=1, title="Policy", purpose="Synthesize policy evidence", target_evidence_roles=["contradictions"]),
        SectionPlan(order=2, title="Gaps", purpose="Demonstrate coverage gap", target_evidence_roles=[]),
    ])
    assembler.assemble_all_sections = AsyncMock(return_value={
        1: EvidencePacket(
            topic_name="Authority Mission",
            section_title="Policy",
            section_objective="Synthesize policy evidence",
            atoms=[
                {"global_id": "A1", "text": "Feature flag evidence 1 for staged rollout safety."},
                {"global_id": "A2", "text": "Feature flag evidence 2 for staged rollout safety."},
                {"global_id": "A3", "text": "Feature flag evidence 3 for staged rollout safety."},
            ],
            contradictions=[{
                "contradiction_set_id": contradiction_set_id,
                "description": "Rollout policy conflicts on when to disable the flag.",
                "related_authority_record_id": related_auth_id,
                "claim_a": "Disable only after user complaints spike.",
                "claim_b": "Disable immediately on latency regression.",
            }],
            atom_ids_used=atom_ids,
        ),
        2: EvidencePacket(
            topic_name="Authority Mission",
            section_title="Gaps",
            section_objective="Demonstrate coverage gap",
            atoms=[],
            atom_ids_used=[],
        ),
    })

    service = SynthesisService(mock_ollama, None, assembler, adapter)
    await service.generate_master_brief(mission_id)

    authority_record_id = f"dar_{mission_id[:8]}"
    authority_row = await adapter.pg.fetch_one("authority.authority_records", {"authority_record_id": authority_record_id})
    assert authority_row is not None

    status = parse_json(authority_row["status_json"])
    advisory = parse_json(authority_row["advisory_layer_json"])
    reuse = parse_json(authority_row["reuse_json"])
    synthesis = parse_json(authority_row["synthesis_layer_json"])
    atom_layer = parse_json(authority_row["atom_layer_json"])

    assert status["maturity"] == "contested"
    assert status["contradiction_count"] == 1
    assert status["advisory_count"] == 2
    assert synthesis["insufficient_sections"] == ["Gaps"]
    assert atom_layer["core_atom_ids"] == atom_ids
    assert advisory["major_contradictions"] == ["Rollout policy conflicts on when to disable the flag."]
    assert advisory["coverage_gaps"] == ["Gaps"]
    assert reuse["ready_for_application"] is False
    assert reuse["reusable_section_count"] == 1

    artifacts = await adapter.pg.fetch_many("authority.synthesis_artifacts", {"authority_record_id": authority_record_id})
    assert len(artifacts) == 1
    artifact_id = artifacts[0]["artifact_id"]

    sections = await adapter.pg.fetch_many(
        "authority.synthesis_sections",
        {"artifact_id": artifact_id},
        order_by="section_order ASC",
    )
    assert [section["section_name"] for section in sections] == ["Policy", "Gaps"]
    assert sections[1]["summary"] == "[INSUFFICIENT EVIDENCE FOR SECTION]"

    citations = await adapter.pg.fetch_many("authority.synthesis_citations", {"artifact_id": artifact_id})
    assert sorted(citation["atom_id"] for citation in citations) == atom_ids

    core_rows = await adapter.pg.fetch_many(
        "authority.authority_core_atoms",
        {"authority_record_id": authority_record_id},
        order_by="rank ASC",
    )
    assert [row["atom_id"] for row in core_rows] == atom_ids

    contradiction_rows = await adapter.pg.fetch_many(
        "authority.authority_contradictions",
        {"authority_record_id": authority_record_id},
    )
    assert [row["contradiction_set_id"] for row in contradiction_rows] == [contradiction_set_id]

    related_rows = await adapter.pg.fetch_many(
        "authority.authority_related_records",
        {"authority_record_id": authority_record_id},
    )
    assert related_rows == [{
        "authority_record_id": authority_record_id,
        "related_authority_record_id": related_auth_id,
        "relation_type": "contradiction_context",
    }]

    advisory_rows = await adapter.pg.fetch_many(
        "authority.authority_advisories",
        {"authority_record_id": authority_record_id},
        order_by="priority DESC, advisory_id ASC",
    )
    assert [row["advisory_type"] for row in advisory_rows] == ["contradiction_risk", "coverage_gap"]
    contradiction_metadata = parse_json(advisory_rows[0]["metadata_json"])
    assert contradiction_metadata["contradiction_set_id"] == contradiction_set_id
    assert contradiction_metadata["claim_a"] == "Disable only after user complaints spike."
