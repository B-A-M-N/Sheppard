"""
Tests for concurrent section assembly in EvidenceAssembler.
Covers: ordering preservation, atom_ids_used determinism, error handling, concurrency limit.
Created: Phase 12-02, Plan 01 (scaffolding for Plan 02 implementation).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from research.reasoning.assembler import (
    EvidenceAssembler, EvidencePacket, SectionPlan, RETRIEVAL_CONCURRENCY_LIMIT
)


class TestConcurrentAssembly:
    """Tests for assemble_all_sections concurrent retrieval."""

    @pytest.fixture
    def assembler(self):
        """Create an EvidenceAssembler with mocked dependencies."""
        ollama = MagicMock()
        memory = MagicMock()
        retriever = MagicMock()
        adapter = MagicMock()
        return EvidenceAssembler(ollama=ollama, memory=memory, retriever=retriever, adapter=adapter)

    @pytest.fixture
    def sample_sections(self):
        """Create sample SectionPlan objects for testing."""
        return [
            SectionPlan(order=i, title=f"Section {i}", purpose=f"Purpose {i}", target_evidence_roles=["definitions"])
            for i in range(1, 9)  # 8 sections
        ]

    @pytest.mark.asyncio
    async def test_concurrent_build_preserves_section_order(self, assembler, sample_sections):
        """Concurrent assemble_all_sections returns packets keyed by section.order."""
        mock_context = MagicMock()
        mock_context.all_items = []
        assembler.retriever.retrieve = AsyncMock(return_value=mock_context)
        assembler.memory = None

        result = await assembler.assemble_all_sections("mission1", "TestTopic", sample_sections)

        assert len(result) == 8
        for i in range(1, 9):
            assert i in result, f"Section order {i} missing from result"

    @pytest.mark.asyncio
    async def test_concurrent_produces_identical_atom_ids_as_sequential(self, assembler, sample_sections):
        """atom_ids_used from concurrent execution matches sequential execution.

        This confirms the CONTEXT.md 'global re-sort' invariant is satisfied by the
        per-section design: build_evidence_packet already sorts atoms by global_id
        within each section, and assemble_all_sections preserves per-section packets
        independently, so atom_ids_used are byte-identical to sequential execution.
        (RESEARCH.md Open Question #1: interpret global re-sort as per-section atom
        sort plus section-order preservation -- do NOT add cross-section dedup.)
        """
        def make_mock_item(atom_id: str, content: str, citation_key: str):
            item = MagicMock()
            item.metadata = {"atom_id": atom_id}
            item.content = content
            item.item_type = "atom"
            item.source = "test"
            item.citation_key = citation_key
            return item

        call_count = [0]
        section_orders = [s.order for s in sorted(sample_sections, key=lambda s: s.order)]

        async def mock_retrieve(query):
            idx = call_count[0] % len(section_orders)
            order = section_orders[idx]
            call_count[0] += 1
            ctx = MagicMock()
            ctx.all_items = [
                make_mock_item(f"atom_{order}_b", f"Content B for section {order}", f"B{order}"),
                make_mock_item(f"atom_{order}_a", f"Content A for section {order}", f"A{order}"),
            ]
            return ctx

        assembler.retriever.retrieve = mock_retrieve
        assembler.memory = None

        # Sequential execution
        call_count[0] = 0
        sequential_packets = {}
        for section in sorted(sample_sections, key=lambda s: s.order):
            packet = await assembler.build_evidence_packet("mission1", "TestTopic", section)
            sequential_packets[section.order] = packet

        # Concurrent execution
        call_count[0] = 0
        concurrent_packets = await assembler.assemble_all_sections("mission1", "TestTopic", sample_sections)

        for order in range(1, 9):
            seq_ids = sequential_packets[order].atom_ids_used
            con_ids = concurrent_packets[order].atom_ids_used
            assert len(seq_ids) == len(con_ids), \
                f"Section {order}: sequential has {len(seq_ids)} atoms, concurrent has {len(con_ids)}"
            assert seq_ids == con_ids, \
                f"Section {order}: atom_ids_used differ. Sequential: {seq_ids}, Concurrent: {con_ids}"

    @pytest.mark.asyncio
    async def test_single_section_failure_returns_empty_packet(self, assembler, sample_sections):
        """If one section's retrieval raises, its packet is empty; others succeed."""
        mock_context = MagicMock()
        mock_context.all_items = []
        call_count = [0]

        async def mock_retrieve(query):
            call_count[0] += 1
            if call_count[0] == 3:
                raise RuntimeError("Simulated retrieval failure")
            return mock_context

        assembler.retriever.retrieve = mock_retrieve
        assembler.memory = None

        result = await assembler.assemble_all_sections("mission1", "TestTopic", sample_sections)

        assert len(result) == 8, f"Expected 8 sections, got {len(result)}"
        for order in range(1, 9):
            assert order in result
            assert isinstance(result[order], EvidencePacket), \
                f"Section {order} is not an EvidencePacket: {type(result[order])}"
        # At least one section should have empty atoms (the one that failed)
        empty_sections = [order for order in result if result[order].atoms == []]
        assert len(empty_sections) >= 1, "At least one section should have empty atoms after failure"

    @pytest.mark.asyncio
    async def test_concurrency_limit_constant_defined(self):
        """RETRIEVAL_CONCURRENCY_LIMIT is defined and equals 8."""
        assert RETRIEVAL_CONCURRENCY_LIMIT == 8


class TestTimingInstrumentation:
    """Tests that per-section timing is logged."""

    @pytest.fixture
    def assembler(self):
        ollama = MagicMock()
        memory = MagicMock()
        retriever = MagicMock()
        adapter = MagicMock()
        return EvidenceAssembler(ollama=ollama, memory=memory, retriever=retriever, adapter=adapter)

    @pytest.mark.asyncio
    async def test_build_evidence_packet_logs_timing(self, assembler):
        """build_evidence_packet logs retrieval timing via logger.debug."""
        mock_context = MagicMock()
        mock_context.all_items = []
        assembler.retriever.retrieve = AsyncMock(return_value=mock_context)
        section = SectionPlan(order=1, title="Test", purpose="test", target_evidence_roles=["definitions"])
        with patch("research.reasoning.assembler.logger") as mock_logger:
            await assembler.build_evidence_packet("m1", "Topic", section)
            debug_calls = [str(c) for c in mock_logger.debug.call_args_list]
            assert any("retrieval:" in c.lower() or "ms" in c.lower() for c in debug_calls), \
                f"Expected timing log, got: {debug_calls}"
