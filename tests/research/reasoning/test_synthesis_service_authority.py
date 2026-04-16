import pytest

from src.research.reasoning.synthesis_service import SynthesisService
from src.research.reasoning.assembler import SectionPlan, EvidencePacket


class FakeAdapter:
    def __init__(self):
        self.core_atom_calls = []
        self.artifacts = []
        self.sections = []
        self.citations = []

    async def get_mission(self, mission_id):
        return {"title": "Topic", "domain_profile_id": "profile-1"}

    async def get_authority_record(self, authority_record_id):
        return {"authority_record_id": authority_record_id}

    async def upsert_authority_record(self, row):
        return None

    async def set_authority_core_atoms(self, authority_record_id, rows):
        self.core_atom_calls.append((authority_record_id, rows))

    async def store_synthesis_artifact(self, artifact):
        self.artifacts.append(artifact)

    async def store_synthesis_sections(self, sections):
        self.sections.extend(sections)

    async def store_synthesis_citations(self, citations):
        self.citations.extend(citations)


class FakeAssembler:
    async def generate_section_plan(self, topic_name):
        return [SectionPlan(order=1, title="Section", purpose="Purpose", target_evidence_roles=[])]

    async def assemble_all_sections(self, mission_id, topic_name, plan):
        return {
            1: EvidencePacket(
                topic_name=topic_name,
                section_title="Section",
                section_objective="Purpose",
                atoms=[{"global_id": "[A1]", "text": "Atom one."}],
                atom_ids_used=["atom-2", "atom-1"],
            )
        }


class FakeArchivist:
    async def write_section(self, packet, previous_context):
        return "Grounded sentence. [A1]"


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

    report = await service.generate_master_brief("mission-1234")

    assert report is not None
    assert len(adapter.core_atom_calls) == 1
    authority_record_id, rows = adapter.core_atom_calls[0]
    assert authority_record_id == "dar_mission-"
    assert rows == [
        {"atom_id": "atom-1", "position_rank": 1, "role": "core"},
        {"atom_id": "atom-2", "position_rank": 2, "role": "core"},
    ]
