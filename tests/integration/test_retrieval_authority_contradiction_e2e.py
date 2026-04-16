import uuid
from unittest.mock import AsyncMock

import pytest

from .test_knowledge_pipeline import adapter_real, compute_hash
from src.research.reasoning.retriever import RetrievalQuery
from src.research.reasoning.v3_retriever import V3Retriever


@pytest.mark.asyncio
async def test_retrieval_authority_contradiction_e2e(adapter_real):
    adapter = adapter_real
    suffix = uuid.uuid4().hex[:6]
    topic_id = f"topic-ret-{suffix}"
    profile_id = f"profile-ret-{suffix}"
    authority_record_id = f"dar-ret-{suffix}"
    contradiction_set_id = f"contra-ret-{suffix}"

    await adapter.pg.insert_row("config.domain_profiles", {
        "profile_id": profile_id, "name": "Retrieval", "domain_type": "technical", "description": "Retrieval e2e", "config_json": "{}"
    })
    await adapter.pg.insert_row("mission.research_missions", {
        "mission_id": topic_id, "topic_id": topic_id, "domain_profile_id": profile_id,
        "title": "Feature Flags", "objective": "Validate retrieval", "status": "active"
    })

    source_id = f"src-ret-{suffix}"
    chunk_id = f"chk-ret-{suffix}"
    url = f"https://example.com/retrieval/{suffix}"
    await adapter.pg.insert_row("corpus.sources", {
        "source_id": source_id, "mission_id": topic_id, "topic_id": topic_id,
        "url": url, "normalized_url": url, "normalized_url_hash": compute_hash(url),
        "source_class": "web", "status": "fetched", "trust_score": 0.88
    })
    await adapter.pg.insert_row("corpus.chunks", {
        "chunk_id": chunk_id, "source_id": source_id, "mission_id": topic_id, "topic_id": topic_id,
        "chunk_index": 0, "chunk_hash": compute_hash(f"retrieval-{suffix}"),
        "inline_text": "Feature flags improve safety when rollouts are staged and reversions are fast."
    })

    core_atom_id = f"atom-ret-core-{suffix}"
    related_atom_id = f"atom-ret-related-{suffix}"
    other_atom_id = f"atom-ret-other-{suffix}"
    atom_payloads = [
        (core_atom_id, "Feature flags require staged rollout safety checks.", authority_record_id, 0.95, 0.95),
        (related_atom_id, "Rollback speed determines whether a flag is safe to leave enabled.", None, 0.82, 0.65),
        (other_atom_id, "Disable immediately on latency regression.", None, 0.84, 0.7),
    ]
    for atom_id, statement, authority_id, confidence, importance in atom_payloads:
        await adapter.store_atom_with_evidence({
            "atom_id": atom_id,
            "mission_id": topic_id,
            "topic_id": topic_id,
            "domain_profile_id": profile_id,
            "authority_record_id": authority_id,
            "atom_type": "claim",
            "title": statement.split(".")[0],
            "statement": statement,
            "confidence": confidence,
            "importance": importance,
            "novelty": 0.3,
        }, [{
            "source_id": source_id,
            "chunk_id": chunk_id,
            "evidence_strength": 1.0,
            "supports_statement": True,
        }])

    await adapter.replace_atom_relationships(core_atom_id, [{
        "related_atom_id": related_atom_id,
        "relation_type": "supports",
        "metadata_json": {},
    }])
    await adapter.upsert_authority_record({
        "authority_record_id": authority_record_id,
        "topic_id": topic_id,
        "domain_profile_id": profile_id,
        "title": "Authority: Feature Flags",
        "canonical_title": "Feature Flags",
        "scope_json": {"framing_statement": "Feature flag governance for staged rollout safety."},
        "status_json": {"maturity": "synthesized", "confidence": 0.93, "freshness": "current"},
        "atom_layer_json": {"core_atom_ids": [core_atom_id], "related_atom_ids": [related_atom_id]},
        "advisory_layer_json": {"decision_rules": ["Prefer staged rollout over immediate full release."]},
    })
    await adapter.create_contradiction_set({
        "contradiction_set_id": contradiction_set_id,
        "topic_id": topic_id,
        "authority_record_id": authority_record_id,
        "summary": "Flag disable threshold is contested.",
        "resolution_status": "unresolved",
    })
    await adapter.add_contradiction_members(contradiction_set_id, [
        {"atom_id": core_atom_id, "position_label": "claim_a"},
        {"atom_id": other_atom_id, "position_label": "claim_b"},
    ])

    adapter.chroma.query = AsyncMock(side_effect=[
        {"documents": [[]], "metadatas": [[]], "distances": [[]]},
        {
            "documents": [["Authority: Feature Flags\nFeature flag governance for staged rollout safety."]],
            "metadatas": [[{
                "authority_record_id": authority_record_id,
                "topic_id": topic_id,
                "confidence": 0.93,
                "maturity": "synthesized",
            }]],
            "distances": [[0.04]],
        },
    ])

    retriever = V3Retriever(adapter)
    ctx = await retriever.retrieve(
        RetrievalQuery(text="feature flag staged rollout safety", topic_filter=topic_id, max_results=6)
    )

    assert any(item.item_type == "authority" for item in ctx.definitions)
    authority_hit = next(item for item in ctx.definitions if item.item_type == "authority")
    assert authority_hit.metadata["authority_record_id"] == authority_record_id
    assert authority_hit.metadata["maturity"] == "synthesized"

    assert any(item.item_type == "contradiction" for item in ctx.contradictions)
    contradiction_hit = next(item for item in ctx.contradictions if item.item_type == "contradiction")
    assert contradiction_hit.metadata["contradiction_set_id"] == contradiction_set_id

    evidence_by_id = {
        item.metadata.get("atom_id"): item
        for item in ctx.evidence
        if item.metadata and item.metadata.get("atom_id")
    }
    assert core_atom_id in evidence_by_id
    assert related_atom_id in evidence_by_id
