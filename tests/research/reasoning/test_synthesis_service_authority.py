import pytest
from unittest.mock import AsyncMock, MagicMock

from src.research.reasoning.synthesis_service import SynthesisService
from src.research.reasoning.assembler import SectionPlan, EvidencePacket


class FakeAdapter:
    def __init__(self):
        self.core_atom_calls = []
        self.contradiction_calls = []
        self.related_record_calls = []
        self.advisory_calls = []
        self.upsert_calls = []
        self.artifacts = []
        self.sections = []
        self.citations = []

    async def get_mission(self, mission_id):
        return {"title": "Topic", "domain_profile_id": "profile-1"}

    async def get_authority_record(self, authority_record_id):
        return {"authority_record_id": authority_record_id}

    async def upsert_authority_record(self, row):
        self.upsert_calls.append(row)

    async def set_authority_core_atoms(self, authority_record_id, rows):
        self.core_atom_calls.append((authority_record_id, rows))

    async def set_authority_contradictions(self, authority_record_id, rows):
        self.contradiction_calls.append((authority_record_id, rows))

    async def set_authority_related_records(self, authority_record_id, rows):
        self.related_record_calls.append((authority_record_id, rows))

    async def set_authority_advisories(self, authority_record_id, rows):
        self.advisory_calls.append((authority_record_id, rows))

    async def store_synthesis_artifact(self, artifact):
        self.artifacts.append(artifact)

    async def store_synthesis_sections(self, sections):
        self.sections.extend(sections)

    async def store_synthesis_citations(self, citations):
        self.citations.extend(citations)

    async def list_synthesis_artifacts(self, auth_id):
        return []


class FakeAssembler:
    async def generate_section_plan(self, topic_name):
        return [SectionPlan(order=1, title="Section", purpose="Purpose", target_evidence_roles=[])]

    async def assemble_all_sections(self, mission_id, topic_name, plan):
        return {
            1: EvidencePacket(
                topic_name=topic_name,
                section_title="Section",
                section_objective="Purpose",
                atoms=[{"global_id": "A1", "text": "Atom one."}],
                contradictions=[{
                    "contradiction_set_id": "contra-1",
                    "description": "Two operational recommendations disagree.",
                    "related_authority_record_id": "auth-related-1",
                    "claim_a": "Enable feature flag.",
                    "claim_b": "Disable feature flag.",
                }],
                atom_ids_used=["atom-2", "atom-1"],
            )
        }


class FakeArchivist:
    async def write_section(self, packet, previous_context):
        return "Atom one [A1]."


@pytest.mark.asyncio
async def test_generate_master_brief_populates_authority_core_atoms():
    adapter = FakeAdapter()
    service = SynthesisService(
        ollama=None,
        memory=None,
        assembler=FakeAssembler(),
        adapter=adapter,
    )
    service.archivist = FakeArchivist()

    mission_id = "mission-1234"
    report = await service.generate_master_brief(mission_id)

    assert report is not None
    
    # 1. Verify upsert_authority_record call
    # It should be called to update the atom layer
    assert len(adapter.upsert_calls) >= 1
    # The last call should contain the core_atom_ids
    atom_layer_upsert = adapter.upsert_calls[-1]
    assert atom_layer_upsert["authority_record_id"] == f"dar_{mission_id[:8]}"
    assert atom_layer_upsert["atom_layer_json"]["core_atom_ids"] == ["atom-1", "atom-2"]
    assert atom_layer_upsert["topic_id"] == mission_id
    assert atom_layer_upsert["domain_profile_id"] == "profile-1"
    assert atom_layer_upsert["status_json"]["maturity"] == "contested"
    assert atom_layer_upsert["status_json"]["contradiction_count"] == 1
    assert atom_layer_upsert["reuse_json"]["ready_for_application"] is True
    assert atom_layer_upsert["synthesis_layer_json"]["master_brief_artifact_id"]
    assert atom_layer_upsert["advisory_layer_json"]["major_contradictions"] == [
        "Two operational recommendations disagree."
    ]

    # 2. Verify set_authority_core_atoms call
    assert len(adapter.core_atom_calls) == 1
    authority_record_id, rows = adapter.core_atom_calls[0]
    assert authority_record_id == f"dar_{mission_id[:8]}"
    # Payload changed to {"atom_id": aid, "rank": idx, "reason": "Used in master brief"}
    # And input IDs were sorted: atom-1, atom-2
    assert rows == [
        {"atom_id": "atom-1", "rank": 0, "reason": "Used in master brief"},
        {"atom_id": "atom-2", "rank": 1, "reason": "Used in master brief"},
    ]

    # 3. Verify contradiction calls
    assert adapter.contradiction_calls == [
        (f"dar_{mission_id[:8]}", [{"contradiction_set_id": "contra-1"}])
    ]

    assert atom_layer_upsert["status_json"]["advisory_count"] == 1

    # 4. Verify related-record and advisory writes
    assert adapter.related_record_calls == [
        (
            f"dar_{mission_id[:8]}",
            [{"related_authority_record_id": "auth-related-1", "relation_type": "contradiction_context"}],
        )
    ]
    authority_record_id, advisories = adapter.advisory_calls[0]
    assert authority_record_id == f"dar_{mission_id[:8]}"
    assert advisories == [
        {
            "advisory_type": "contradiction_risk",
            "statement": "Two operational recommendations disagree.",
            "priority": 90,
            "metadata_json": {
                "contradiction_set_id": "contra-1",
                "claim_a": "Enable feature flag.",
                "claim_b": "Disable feature flag.",
            },
        }
    ]


def test_build_authority_maturation_update_dedupes_related_records_and_adds_coverage_gap():
    service = SynthesisService(ollama=None, memory=None, assembler=MagicMock(), adapter=None)

    result = service._build_authority_maturation_update(
        authority_record_id="dar_topic123",
        mission_id="topic-123",
        domain_profile_id="profile-1",
        topic_name="Topic",
        artifact_id="artifact-1",
        all_atom_ids=["atom-1", "atom-2"],
        sections_to_store=[
            {"section_name": "Conflicts", "summary": "Some prose"},
            {"section_name": "Open Issues", "summary": "[INSUFFICIENT EVIDENCE FOR SECTION]"},
        ],
        contradictions=[
            {
                "contradiction_set_id": "contra-1",
                "description": "Operators disagree about rollback timing.",
                "related_authority_record_id": "auth-related-2",
                "claim_a": "Rollback after user complaints spike.",
                "claim_b": "Rollback on first latency regression.",
            },
            {
                "contradiction_set_id": "contra-2",
                "description": "Operators disagree about rollback timing.",
                "related_authority_record_id": "auth-related-2",
                "other_authority_record_id": "auth-related-3",
                "claim_a": "Rollback after user complaints spike.",
                "claim_b": "Rollback on first latency regression.",
            },
        ],
    )

    record = result["record"]
    assert record["status_json"]["maturity"] == "contested"
    assert record["status_json"]["contradiction_count"] == 1
    assert record["status_json"]["advisory_count"] == 2
    assert record["reuse_json"]["ready_for_application"] is False
    assert record["synthesis_layer_json"]["insufficient_sections"] == ["Open Issues"]
    assert record["advisory_layer_json"]["major_contradictions"] == [
        "Operators disagree about rollback timing."
    ]

    assert result["related_records"] == [
        {"related_authority_record_id": "auth-related-2", "relation_type": "contradiction_context"},
        {"related_authority_record_id": "auth-related-3", "relation_type": "contradiction_context"},
    ]
    assert result["advisories"] == [
        {
            "advisory_type": "contradiction_risk",
            "statement": "Operators disagree about rollback timing.",
            "priority": 90,
            "metadata_json": {
                "contradiction_set_id": "contra-1",
                "claim_a": "Rollback after user complaints spike.",
                "claim_b": "Rollback on first latency regression.",
            },
        },
        {
            "advisory_type": "coverage_gap",
            "statement": "Section 'Open Issues' lacked enough evidence for synthesis.",
            "priority": 70,
            "metadata_json": {"section_name": "Open Issues"},
        },
    ]
