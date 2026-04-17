"""Phase 11.1: Unit tests for V3 truth contract invariants."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.research.reasoning.assembler import EvidenceAssembler, EvidencePacket, SectionPlan
from src.research.reasoning.v3_retriever import V3Retriever
from src.research.reasoning.retriever import RetrievalQuery, RetrievedItem
from src.research.reasoning.synthesis_service import SynthesisService, MIN_EVIDENCE_FOR_SECTION
from src.research.archivist.synth_adapter import ArchivistSynthAdapter
from src.research.domain_schema import SynthesisArtifact


def make_retrieved_item(atom_id, text, citation_key=None):
    """Helper to create a RetrievedItem with atom_id in metadata."""
    meta = {'atom_id': atom_id, 'citation_key': citation_key}
    return RetrievedItem(
        content=text,
        source='test_source',
        strategy='semantic',
        knowledge_level='B',
        item_type='claim',
        relevance_score=0.9,
        citation_key=citation_key,
        metadata=meta
    )


# --- Invariant 1: V3Retriever ---

@pytest.mark.asyncio
async def test_assembler_uses_v3_retriever():
    """EvidenceAssembler must use V3Retriever and pass mission_filter."""
    mock_retriever = MagicMock(spec=V3Retriever)
    mock_retriever.retrieve = AsyncMock(return_value=MagicMock(is_empty=False, evidence=[]))
    assembler = EvidenceAssembler(
        ollama=MagicMock(),
        memory=MagicMock(),
        retriever=mock_retriever,
        adapter=None
    )
    section = SectionPlan(order=1, title="Test", purpose="test", target_evidence_roles=[])
    await assembler.build_evidence_packet("mission123", "Topic", section)
    assert mock_retriever.retrieve.called
    query_arg = mock_retriever.retrieve.call_args[0][0]
    assert isinstance(query_arg, RetrievalQuery)
    assert query_arg.mission_filter == "mission123"


# --- Invariant 2: Provenance ---

@pytest.mark.asyncio
async def test_evidence_packet_captures_atom_ids():
    """EvidencePacket must populate atom_ids_used from item metadata."""
    mock_retriever = MagicMock(spec=V3Retriever)
    items = [
        make_retrieved_item("atom1", "Text one", citation_key="A1"),
        make_retrieved_item("atom2", "Text two", citation_key="A2"),
    ]
    mock_retriever.retrieve = AsyncMock(return_value=MagicMock(is_empty=False, all_items=items))
    assembler = EvidenceAssembler(
        ollama=MagicMock(),
        memory=MagicMock(),
        retriever=mock_retriever,
        adapter=None
    )
    section = SectionPlan(order=1, title="Test", purpose="test", target_evidence_roles=[])
    packet = await assembler.build_evidence_packet("mission123", "Topic", section)
    assert "atom1" in packet.atom_ids_used
    assert "atom2" in packet.atom_ids_used
    assert len(packet.atoms) == 2
    # Ensure ordering corresponds to sorted global_id
    assert [a['global_id'] for a in packet.atoms] == ['[A1]', '[A2]']


# --- Invariant 3: Mission Isolation ---

@pytest.mark.asyncio
async def test_synthesis_service_propagates_mission_id():
    """generate_master_brief must pass mission_id to storage calls."""
    mock_ollama = MagicMock()
    mock_ollama.complete = AsyncMock(return_value="This section provides evidence [A1].")
    mock_assembler = MagicMock()
    mock_adapter = MagicMock()

    # Mission lookup
    mock_adapter.get_mission = AsyncMock(return_value={
        'mission_id': 'mission123',
        'title': 'Test Mission',
        'topic_id': 'mission123'
    })

    # Authority record lookup (for auto-create)
    mock_adapter.get_authority_record = AsyncMock(return_value=None)  # Not exists, will create
    mock_adapter.upsert_authority_record = AsyncMock(return_value=None)

    # Storage methods must be async - support both singular and plural
    mock_adapter.store_synthesis_artifact = AsyncMock(return_value=None)
    mock_adapter.store_synthesis_section = AsyncMock(return_value=None)
    mock_adapter.store_synthesis_sections = AsyncMock(return_value=None)
    mock_adapter.store_synthesis_citations = AsyncMock(return_value=None)

    # Section plan
    mock_assembler.generate_section_plan = AsyncMock(return_value=[
        SectionPlan(order=1, title="Section 1", purpose="purpose", target_evidence_roles=[])
    ])

    # Evidence packet with enough atoms
    mock_packet = EvidencePacket(
        topic_name="Test Mission",
        section_title="Section 1",
        section_objective="purpose",
        atoms=[{'global_id': '[A1]', 'text': 'Evidence', 'type': 'claim'}],
        atom_ids_used=['atom1']
    )
    mock_assembler.build_evidence_packet = AsyncMock(return_value=mock_packet)
    mock_assembler.assemble_all_sections = AsyncMock(return_value={1: mock_packet})

    # Archivist returns valid prose (must have lexical overlap and citation)
    mock_archivist = MagicMock(spec=ArchivistSynthAdapter)
    mock_archivist.write_section = AsyncMock(return_value="This section provides evidence [A1].")

    with patch('src.research.reasoning.synthesis_service.ArchivistSynthAdapter', return_value=mock_archivist):
        service = SynthesisService(
            ollama=mock_ollama,
            memory=None,
            assembler=mock_assembler,
            adapter=mock_adapter
        )
        await service.generate_master_brief("mission123")

    # Section storage should include mission_id and atom_ids_used at top level
    sections_calls = mock_adapter.store_synthesis_sections.call_args_list
    assert len(sections_calls) >= 1
    sections_stored = sections_calls[0][0][0]  # First call, first arg (list)
    assert isinstance(sections_stored, list) and len(sections_stored) > 0
    assert sections_stored[0]['mission_id'] == 'mission123'
    assert 'atom_ids_used' in sections_stored[0]  # top-level provenance field

    # Authority record should have been created (upserted)
    assert mock_adapter.upsert_authority_record.called

    # Artifact storage should include mission_id
    artifact_store_call = mock_adapter.store_synthesis_artifact.call_args[0][0]
    assert artifact_store_call['mission_id'] == 'mission123'

    # Citations storage should include the atom_id
    assert mock_adapter.store_synthesis_citations.called
    citations = mock_adapter.store_synthesis_citations.call_args[0][0]
    assert any(c['atom_id'] == 'atom1' for c in citations)


# --- Invariant 4 & 5: Prompt & Validator ---

def test_archivist_prompt_constraints():
    """Prompt must not contain MINIMUM 1000 WORDS and must forbid inference."""
    from src.research.archivist.synth_adapter import SCHOLARLY_ARCHIVIST_PROMPT
    prompt = SCHOLARLY_ARCHIVIST_PROMPT.upper()
    assert "MINIMUM 1000 WORDS" not in SCHOLARLY_ARCHIVIST_PROMPT
    assert "NO INFERENCE" in prompt
    assert "PER-SENTENCE CITATION" in prompt


def test_grounding_validator_logic():
    """Validator must enforce per-sentence citation and lexical support."""
    from src.research.reasoning.synthesis_service import SynthesisService
    # We create a service instance without needing real dependencies to test _validate_grounding
    mock_service = SynthesisService(
        ollama=MagicMock(),
        memory=None,
        assembler=MagicMock(),
        adapter=MagicMock()
    )
    packet = EvidencePacket(
        topic_name="Test",
        section_title="Test",
        section_objective="test",
        atoms=[
            {'global_id': '[A1]', 'text': 'The temperature is 300 degrees Celsius.', 'type': 'claim'}
        ],
        atom_ids_used=['atom1']
    )
    # Valid sentence with citation and word overlap
    valid_prose = "The temperature is 300 degrees Celsius [A1]."
    assert mock_service._validate_grounding(valid_prose, packet) is True

    # Missing citation entirely
    invalid_missing = "The temperature is 300 degrees Celsius."
    assert mock_service._validate_grounding(invalid_missing, packet) is False

    # Citation but no lexical overlap
    invalid_overlap = "Something entirely different [A1]."
    assert mock_service._validate_grounding(invalid_overlap, packet) is False

    # Multiple sentences, one bad -> fail
    mixed = "First sentence is good [A1]. This one has no citation."
    assert mock_service._validate_grounding(mixed, packet) is False


# --- Invariant 6: Determinism ---

def test_model_router_synthesis_config():
    from src.llm.model_router import ModelRouter, TaskType
    router = ModelRouter()
    synth_cfg = router.get(TaskType.SYNTHESIS)
    assert synth_cfg.temperature == 0.0
    assert synth_cfg.seed is not None
    assert isinstance(synth_cfg.seed, int)

@pytest.mark.asyncio
async def test_atom_order_sorted():
    """build_evidence_packet must return atoms sorted by global_id for determinism."""
    mock_retriever = MagicMock(spec=V3Retriever)
    items = [
        make_retrieved_item("atom2", "Text B", citation_key="B"),
        make_retrieved_item("atom1", "Text A", citation_key="A"),
    ]
    mock_retriever.retrieve = AsyncMock(return_value=MagicMock(is_empty=False, all_items=items))
    assembler = EvidenceAssembler(
        ollama=MagicMock(),
        memory=MagicMock(),
        retriever=mock_retriever,
        adapter=None
    )
    section = SectionPlan(order=1, title="Test", purpose="test", target_evidence_roles=[])
    packet = await assembler.build_evidence_packet("mission123", "Topic", section)
    # global_ids should be sorted alphabetically: [A] before [B]
    gids = [a['global_id'] for a in packet.atoms]
    assert gids == ['[A]', '[B]']
    # Corresponding atom_ids_used order should match
    assert packet.atom_ids_used == ['atom1', 'atom2']


# --- Invariant 7: Insufficient Evidence Fallback ---

@pytest.mark.asyncio
async def test_insufficient_evidence_skips_synthesis():
    """When evidence is zero, archivist.write_section must not be called."""
    mock_ollama = MagicMock()
    mock_assembler = MagicMock()
    mock_adapter = MagicMock()

    mock_adapter.get_mission = AsyncMock(return_value={
        'mission_id': 'mission123',
        'title': 'Test Mission',
        'topic_id': 'mission123'
    })
    mock_adapter.get_authority_record = AsyncMock(return_value=None)
    mock_adapter.upsert_authority_record = AsyncMock(return_value=None)
    mock_adapter.store_synthesis_artifact = AsyncMock(return_value=None)
    mock_adapter.store_synthesis_sections = AsyncMock(return_value=None)
    mock_adapter.store_synthesis_citations = AsyncMock(return_value=None)

    mock_assembler.generate_section_plan = AsyncMock(return_value=[
        SectionPlan(order=1, title="Section 1", purpose="purpose", target_evidence_roles=[])
    ])

    # Packet with zero atoms
    mock_packet = EvidencePacket(
        topic_name="Test Mission",
        section_title="Section 1",
        section_objective="purpose",
        atoms=[],
        atom_ids_used=[]
    )
    mock_assembler.build_evidence_packet = AsyncMock(return_value=mock_packet)
    mock_assembler.assemble_all_sections = AsyncMock(return_value={1: mock_packet})

    with patch('src.research.reasoning.synthesis_service.ArchivistSynthAdapter') as MockArchivist:
        mock_archivist = MagicMock()
        MockArchivist.return_value = mock_archivist
        service = SynthesisService(
            ollama=mock_ollama,
            memory=None,
            assembler=mock_assembler,
            adapter=mock_adapter
        )
        await service.generate_master_brief("mission123")

    # Archivist should NOT be called
    mock_archivist.write_section.assert_not_called()
    # Authority record should be created (auto-create)
    assert mock_adapter.upsert_authority_record.called
    # Section storage should contain placeholder (summary field)
    sections_calls = mock_adapter.store_synthesis_sections.call_args_list
    assert len(sections_calls) >= 1
    sections_stored = sections_calls[0][0][0]
    placeholder_section = sections_stored[0]
    assert "[INSUFFICIENT EVIDENCE FOR SECTION]" in placeholder_section['summary']
    # atom_ids_used should be empty list
    assert placeholder_section['atom_ids_used'] == []
    # No citations should be stored
    mock_adapter.store_synthesis_citations.assert_not_called()
