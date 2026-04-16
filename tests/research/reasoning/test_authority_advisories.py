from unittest.mock import MagicMock

from src.research.reasoning.synthesis_service import SynthesisService


def test_build_authority_maturation_update_creates_advisories_and_related_records():
    service = SynthesisService(ollama=None, memory=None, assembler=MagicMock(), adapter=None)

    result = service._build_authority_maturation_update(
        authority_record_id="dar-topic",
        mission_id="topic-1",
        domain_profile_id="profile-1",
        topic_name="Topic 1",
        artifact_id="artifact-1",
        all_atom_ids=["atom-1", "atom-2", "atom-3"],
        sections_to_store=[
            {"section_name": "Overview", "summary": "Grounded summary"},
            {"section_name": "Disputes", "summary": "[INSUFFICIENT EVIDENCE FOR SECTION]"},
        ],
        contradictions=[
            {
                "contradiction_set_id": "contra-1",
                "description": "Teams disagree about rollback timing.",
                "related_authority_record_id": "auth-2",
                "claim_a": "Rollback after complaints spike.",
                "claim_b": "Rollback immediately on latency regression.",
            }
        ],
    )

    assert result["record"]["status_json"]["maturity"] == "contested"
    assert result["record"]["status_json"]["advisory_count"] == 2
    assert result["record"]["advisory_layer_json"]["major_contradictions"] == [
        "Teams disagree about rollback timing."
    ]
    assert result["record"]["advisory_layer_json"]["coverage_gaps"] == ["Disputes"]
    assert result["related_records"] == [
        {"related_authority_record_id": "auth-2", "relation_type": "contradiction_context"}
    ]
    assert result["advisories"][0]["advisory_type"] == "contradiction_risk"
    assert result["advisories"][1]["advisory_type"] == "coverage_gap"
