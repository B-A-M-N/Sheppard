"""
Integration tests for ChatApp truth-grounded retrieval (Phase 10 PLAN-02).

Tests cover:
- V3Retriever is called for every query
- System prompt contains grounding instructions and citation format
- Responses are buffered before validation; no early yield
- Refusal on empty context (indexing delay)
- Refusal on validation failure
- No bypass via memory_system.search
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from retrieval.retriever import RoleBasedContext, RetrievedItem
# Normal import to get coverage recognized
from src.core.chat import ChatApp, ChatConfig

class ChunkWrap:
    """Mimics the chunk objects from OllamaClient.chat."""
    def __init__(self, content):
        self.content = content


@pytest.fixture
def mock_llm_client():
    client = AsyncMock()
    async def mock_chat(messages, stream=False, persona=None, metadata=None):
        yield ChunkWrap("Mock ")
        yield ChunkWrap("LLM ")
        yield ChunkWrap("response.")
    client.chat = mock_chat
    return client


@pytest.fixture
def mock_v3_retriever():
    vr = MagicMock()
    vr.query = AsyncMock()
    vr.build_context_block = MagicMock(return_value="--- KNOWLEDGE ---\n- Test fact. [A001]\n--- END KNOWLEDGE ---")
    return vr


@pytest.fixture
def mock_system_manager(mock_llm_client):
    sm = MagicMock()
    sm.retriever = None
    sm.ollama = mock_llm_client

    def _build_system_prompt(context, project):
        base = [
            "You are a grounded research assistant.",
            "- Use ONLY the retrieved knowledge to answer. Do not use your general training.",
            "- Every claim must be directly supported by at least one of the provided sources.",
            "- Cite claims inline using the [A###] keys from the knowledge section. Every declarative claim must have a citation.",
            '- If the knowledge does not contain sufficient information to answer, say "I cannot answer based on available knowledge."',
            "- Do not make assumptions or inferences beyond what the sources explicitly state.",
            "- If sources contradict each other, you must acknowledge the disagreement rather than presenting a single definitive answer."
        ]
        if project:
            base.append(f"\nProject context: {project}")
        base.extend([
            "\nUse the following retrieved knowledge to answer the user's query. Cite each claim with the appropriate [A###] key.",
            "\n--- KNOWLEDGE ---",
            context,
            "--- END KNOWLEDGE ---",
            "\nBe precise, technical, and direct."
        ])
        return "\n".join(base)
    sm._build_system_prompt = _build_system_prompt
    return sm


@pytest.mark.asyncio
async def test_v3_retriever_called(mock_v3_retriever, mock_system_manager):
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config, v3_retriever=mock_v3_retriever)
    await app.initialize(system_manager=mock_system_manager)
    # Prepare v3_retriever.query to return a context with evidence
    ctx = RoleBasedContext()
    ctx.evidence = [RetrievedItem(content="Test atom", source="test", strategy="semantic")]
    mock_v3_retriever.query.return_value = ctx
    # Patch validation to pass
    with patch.object(app, '_validate_response', return_value=True):
        # Consume the async generator
        async for _ in app.process_input("Test query"):
            pass
    # Check query called with user input
    mock_v3_retriever.query.assert_awaited_once_with("Test query")


@pytest.mark.asyncio
async def test_system_message_contains_context_and_grounding(mock_v3_retriever, mock_system_manager):
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config, v3_retriever=mock_v3_retriever)
    await app.initialize(system_manager=mock_system_manager)
    ctx = RoleBasedContext()
    item = RetrievedItem(content="Atoms are basic units.", source="test", strategy="semantic")
    ctx.evidence = [item]
    mock_v3_retriever.query.return_value = ctx
    # Use a context block that includes a citation
    context_block = "--- KNOWLEDGE ---\n- Atoms are basic units. [A001]\n--- END KNOWLEDGE ---"
    mock_v3_retriever.build_context_block.return_value = context_block
    # Capture messages sent to LLM
    sent_messages = []
    async def capture_chat(messages, stream=False, persona=None, metadata=None):
        sent_messages.append(messages)
        yield ChunkWrap("Response")
    mock_system_manager.ollama.chat = capture_chat
    with patch.object(app, '_validate_response', return_value=True):
        async for _ in app.process_input("Test query"):
            pass
    assert len(sent_messages) == 1
    system_msg = sent_messages[0][0]
    assert system_msg['role'] == 'system'
    content = system_msg['content']
    # Check grounding language
    assert "Use ONLY the retrieved knowledge" in content
    assert "Every claim must be directly supported" in content
    assert "I cannot answer based on available knowledge." in content
    assert "[A001]" in content
    assert "Atoms are basic units." in content


@pytest.mark.asyncio
async def test_response_buffering(mock_v3_retriever, mock_system_manager):
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config, v3_retriever=mock_v3_retriever)
    await app.initialize(system_manager=mock_system_manager)
    ctx = RoleBasedContext()
    ctx.evidence = [RetrievedItem(content="Atom", source="test", strategy="semantic")]
    mock_v3_retriever.query.return_value = ctx
    # Track order of operations
    events = []
    async def fake_chat(messages, stream=False, persona=None, metadata=None):
        events.append("llm_start")
        yield ChunkWrap("Hello ")
        yield ChunkWrap("World")
        events.append("llm_end")
    mock_system_manager.ollama.chat = fake_chat
    def fake_validate(resp, atoms):
        events.append("validate")
        return True
    with patch.object(app, '_validate_response', side_effect=fake_validate):
        yielded = []
        async for resp in app.process_input("Test"):
            yielded.append(resp)
            events.append("yield")
    # Verify order: llm_start -> llm_end -> validate -> yield
    assert events == ["llm_start", "llm_end", "validate", "yield"]
    assert len(yielded) == 1
    assert yielded[0].content == "Hello World"


@pytest.mark.asyncio
async def test_refusal_when_no_atoms(mock_v3_retriever, mock_system_manager):
    config = ChatConfig()
    app = ChatApp(config=config, v3_retriever=mock_v3_retriever)
    await app.initialize(system_manager=mock_system_manager)
    # query returns empty context
    empty_ctx = RoleBasedContext()
    mock_v3_retriever.query.return_value = empty_ctx
    # Should not call LLM
    llm_called = False
    async def fake_chat(messages, stream=False, persona=None, metadata=None):
        nonlocal llm_called
        llm_called = True
        yield ChunkWrap("Should not happen")
    mock_system_manager.ollama.chat = fake_chat
    responses = []
    async for resp in app.process_input("Test query"):
        responses.append(resp)
    assert len(responses) == 1
    assert responses[0].content == "I cannot answer based on available knowledge."
    # response_type is ResponseType.ERROR from the real enum; compare by .value
    assert responses[0].response_type.value == "error"
    assert not llm_called  # LLM not called


@pytest.mark.asyncio
async def test_refusal_when_validation_fails(mock_v3_retriever, mock_system_manager):
    config = ChatConfig()
    app = ChatApp(config=config, v3_retriever=mock_v3_retriever)
    await app.initialize(system_manager=mock_system_manager)
    ctx = RoleBasedContext()
    # create item with citation_key set (simulate after build_context_block)
    item = RetrievedItem(content="Atom content", source="test", strategy="semantic", citation_key="[A001]")
    ctx.evidence = [item]
    mock_v3_retriever.query.return_value = ctx
    # Build context block should also produce a string
    mock_v3_retriever.build_context_block.return_value = "Context with [A001]"
    # LLM returns a response
    async def fake_chat(messages, stream=False, persona=None, metadata=None):
        yield ChunkWrap("Some response")
    mock_system_manager.ollama.chat = fake_chat
    # Patch validation to fail
    with patch.object(app, '_validate_response', return_value=False):
        responses = []
        async for resp in app.process_input("Test query"):
            responses.append(resp)
    assert len(responses) == 1
    assert responses[0].content == "I cannot answer based on available knowledge."
    assert responses[0].response_type.value == "error"


def test_no_memory_system_search_bypass():
    # Static analysis: ensure chat.py has no calls to memory_system.search
    chat_path = Path(__file__).parent.parent / "src" / "core" / "chat.py"
    content = chat_path.read_text()
    assert "memory_system.search" not in content


# --- Additional tests for coverage to exceed 80% on chat module ---

@pytest.mark.asyncio
async def test_validate_response_method_direct():
    """Unit test for ChatApp._validate_response wrapper."""
    app = ChatApp()
    # Use a simple valid case
    atom = RetrievedItem(content="Atom content", source="test", strategy="semantic", citation_key="[A001]")
    response = "Atom content. [A001]"
    # Call real _validate_response
    result = app._validate_response(response, [atom])
    assert result is True

def test_chat_context_add_and_clear():
    """Coverage for ChatContext methods."""
    config = ChatConfig()
    ctx = ChatContext(config)
    # Add messages
    from research.models import Message, MessageRole
    msg1 = Message(role=MessageRole.USER, content="Hello")
    msg2 = Message(role=MessageRole.ASSISTANT, content="Hi")
    ctx.add_message(msg1)
    ctx.add_message(msg2)
    assert len(ctx.messages) == 2
    # Test pop when exceeding max_context_messages
    config.max_context_messages = 1
    ctx.add_message(Message(role=MessageRole.USER, content="Third"))
    assert len(ctx.messages) == 1
    # Clear
    ctx.clear_messages()
    assert len(ctx.messages) == 0

@pytest.mark.asyncio
async def test_perform_research(mock_system_manager):
    """Cover perform_research method."""
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config)
    # Initialize with system_manager (but we need v3_retriever? perform_research uses system_manager.query, not v3_retriever. It doesn't require v3_retriever.
    await app.initialize(system_manager=mock_system_manager)
    # Mock system_manager.query to return a string
    mock_system_manager.query = AsyncMock(return_value="Research results")
    responses = []
    async for resp in app.perform_research("test topic"):
        responses.append(resp)
    assert len(responses) >= 2  # thinking then result
    assert any(r.response_type.value == "thinking" for r in responses)
    assert any(r.response_type.value == "research" for r in responses)
    assert any(r.content == "Research results" for r in responses)

@pytest.mark.asyncio
async def test_get_system_status(mock_system_manager):
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config)
    await app.initialize(system_manager=mock_system_manager)
    mock_system_manager.status = MagicMock(return_value={"models": {"chat": "test-model"}})
    status = await app.get_system_status()
    assert "system" in status
    assert status["system"]["initialized"] is True
    assert "v2_orchestrator" in status

@pytest.mark.asyncio
async def test_memory_storage_enabled(mock_v3_retriever, mock_system_manager):
    """Test that when enable_memory=True, storage and preference extraction are invoked."""
    config = ChatConfig(enable_memory=True)
    app = ChatApp(config=config, v3_retriever=mock_v3_retriever)
    await app.initialize(system_manager=mock_system_manager)
    # Setup v3_retriever to return a valid context
    ctx = RoleBasedContext()
    atom = RetrievedItem(content="Test atom", source="test", strategy="semantic")
    ctx.evidence = [atom]
    mock_v3_retriever.query.return_value = ctx
    # Manually set citation_key for atom (build_context_block would do it)
    atom.citation_key = "[A001]"
    mock_v3_retriever.build_context_block.return_value = f"- {atom.content} [A001]"
    # Mock system_manager.memory with AsyncMock store
    mock_memory = AsyncMock()
    mock_system_manager.memory = mock_memory
    # LLM response that is valid: cite the atom
    async def fake_chat(messages, stream=False, persona=None, metadata=None):
        yield ChunkWrap("Test atom. [A001]")
    mock_system_manager.ollama.chat = fake_chat
    # Do not patch _validate_response; let real validator run (it should pass)
    responses = []
    async for resp in app.process_input("my favorite color is blue"):
        responses.append(resp)
    assert len(responses) == 1
    # Check that memory.store was called at least twice: once for interaction, once for preference
    # Since interaction is always stored, and preference should be extracted due to "favorite color is blue"
    assert mock_memory.store.call_count >= 2
    # Verify interaction memory content
    calls = mock_memory.store.call_args_list
    # First call likely interaction
    interaction_mem = calls[0][0][0]  # first positional arg
    assert "User: my favorite color is blue" in interaction_mem.content
    # Preference call contains color=blue
    pref_mem = calls[1][0][0]
    assert "color=blue" in pref_mem.content


@pytest.mark.asyncio
async def test_indexing_delay_triggers_fallback(mock_v3_retriever, mock_system_manager):
    """TCR 5: Indexing delay (no atoms visible) should cause exact refusal."""
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config, v3_retriever=mock_v3_retriever)
    await app.initialize(system_manager=mock_system_manager)
    # Simulate unindexed atoms: empty context
    empty_ctx = RoleBasedContext()
    mock_v3_retriever.query.return_value = empty_ctx
    # Mock LLM to ensure it is not called
    llm_called = False
    async def fake_chat(messages, stream=False, persona=None, metadata=None):
        nonlocal llm_called
        llm_called = True
        yield ChunkWrap("Should not be called")
    mock_system_manager.ollama.chat = fake_chat
    responses = []
    async for resp in app.process_input("Test query"):
        responses.append(resp)
    assert len(responses) == 1
    assert responses[0].content == "I cannot answer based on available knowledge."
    assert responses[0].response_type.value == "error"
    assert not llm_called


@pytest.mark.asyncio
async def test_contradictions_preserved_in_flow(mock_v3_retriever, mock_system_manager):
    """TCR 7: Contradictory atoms both appear in context; validation passes when LLM response cites both with supporting claims."""
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config, v3_retriever=mock_v3_retriever)
    await app.initialize(system_manager=mock_system_manager)
    # Two contradictory atoms
    ctx = RoleBasedContext()
    atom1 = RetrievedItem(content="The capital of France is Paris.", source="src1", strategy="semantic")
    atom2 = RetrievedItem(content="The capital of France is London.", source="src2", strategy="semantic")
    ctx.evidence = [atom1, atom2]
    mock_v3_retriever.query.return_value = ctx
    # Manually assign citation keys (simulating build_context_block)
    atom1.citation_key = "[A001]"
    atom2.citation_key = "[A002]"
    # Build context block string to be included in system prompt
    mock_v3_retriever.build_context_block.return_value = f"- {atom1.content} [A001]\n- {atom2.content} [A002]"
    # LLM cites both atoms with claims that directly match atom content
    async def fake_chat(messages, stream=False, persona=None, metadata=None):
        yield ChunkWrap("The capital of France is Paris. [A001] ")
        yield ChunkWrap("The capital of France is London. [A002]")
    mock_system_manager.ollama.chat = fake_chat
    # Use real validator to ensure passing
    from retrieval.validator import validate_response_grounding as real_validator
    def custom_validate(resp, atoms):
        return real_validator(resp, atoms).get('is_valid', False)
    with patch.object(app, '_validate_response', side_effect=custom_validate):
        responses = []
        async for resp in app.process_input("Test query"):
            responses.append(resp)
    # Should get a normal response (not refusal)
    assert len(responses) == 1
    content = responses[0].content
    # Both claims should be present and cited
    assert "Paris" in content and "[A001]" in content
    assert "London" in content and "[A002]" in content
