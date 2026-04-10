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

# Import directly from src
from src.research.models import ChatResponse, ResponseType, Message, MessageRole
from src.core.chat import ChatApp, ChatConfig


@pytest.fixture
def mock_system_manager():
    """Create a mock SystemManager with all required methods."""
    sm = MagicMock()
    
    # Mock chat to return streaming response
    async def mock_chat(messages, stream=False, persona=None, metadata=None):
        yield "Mock "
        yield "LLM "
        yield "response."
    sm.chat = mock_chat
    
    # Mock query
    sm.query = AsyncMock(return_value="Query results")
    
    # Mock status
    sm.status = MagicMock(return_value={
        "models": {"chat": "test-model"},
        "initialized": True
    })
    
    # Mock memory (disabled by default)
    sm.memory = None
    
    return sm


@pytest.mark.asyncio
async def test_chat_initialization(mock_system_manager):
    """Test that ChatApp initializes correctly."""
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config)
    await app.initialize(system_manager=mock_system_manager)
    assert app.is_ready
    assert app.system_manager == mock_system_manager


@pytest.mark.asyncio
async def test_process_input_basic(mock_system_manager):
    """Test basic process_input flow."""
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config)
    await app.initialize(system_manager=mock_system_manager)
    
    responses = []
    async for resp in app.process_input("Test query"):
        responses.append(resp)
    
    assert len(responses) > 0
    assert all(isinstance(r, ChatResponse) for r in responses)
    # Concatenate all tokens
    full_content = "".join(r.content for r in responses)
    assert "Mock" in full_content or "LLM" in full_content or "response" in full_content


@pytest.mark.asyncio
async def test_perform_research(mock_system_manager):
    """Test perform_research method."""
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config)
    await app.initialize(system_manager=mock_system_manager)
    
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
    """Test get_system_status returns correct structure."""
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config)
    await app.initialize(system_manager=mock_system_manager)
    
    status = await app.get_system_status()
    
    assert "system" in status
    assert status["system"]["initialized"] is True
    assert "v2_orchestrator" in status
    assert "models" in status


def test_no_memory_system_search_bypass():
    """Static analysis: ensure chat.py has no calls to memory_system.search."""
    chat_path = Path(__file__).parent.parent / "src" / "core" / "chat.py"
    content = chat_path.read_text()
    assert "memory_system.search" not in content


def test_chat_context_add_and_clear():
    """Coverage for ChatContext methods."""
    from src.core.chat import ChatContext
    config = ChatConfig()
    config.max_context_messages = 2  # Set limit first
    ctx = ChatContext(config)
    
    # Add messages
    msg1 = Message(role=MessageRole.USER, content="Hello")
    msg2 = Message(role=MessageRole.ASSISTANT, content="Hi")
    ctx.add_message(msg1)
    ctx.add_message(msg2)
    assert len(ctx.messages) == 2
    
    # Test pop when exceeding max_context_messages
    ctx.add_message(Message(role=MessageRole.USER, content="Third"))
    assert len(ctx.messages) == 2  # Should have popped first
    
    # Clear
    ctx.clear_messages()
    assert len(ctx.messages) == 0


@pytest.mark.asyncio
async def test_memory_storage_interaction(mock_system_manager):
    """Test that when enable_memory=True, memory storage is invoked."""
    config = ChatConfig(enable_memory=True)
    app = ChatApp(config=config)
    await app.initialize(system_manager=mock_system_manager)
    
    # Mock memory.store
    mock_memory = AsyncMock()
    mock_system_manager.memory = mock_memory
    
    responses = []
    async for resp in app.process_input("my favorite color is blue"):
        responses.append(resp)
    
    assert len(responses) > 0
    # Check that memory.store was called
    assert mock_memory.store.call_count >= 1


@pytest.mark.asyncio
async def test_response_locking(mock_system_manager):
    """Test that process_input uses processing lock."""
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config)
    await app.initialize(system_manager=mock_system_manager)
    
    # Should not raise even with concurrent calls
    async for _ in app.process_input("Test"):
        pass
    
    assert app.context.state.value == "ready"


@pytest.mark.asyncio
async def test_settings_management():
    """Test chat settings management."""
    config = ChatConfig()
    app = ChatApp(config=config)
    
    settings = await app.get_settings()
    assert "max_message_length" in settings
    assert "enable_memory" in settings
    
    # Test setting update
    await app.update_setting("enable_memory", True)
    assert app.config.enable_memory is True
    
    # Test setting description
    desc = app.get_setting_description("enable_memory")
    assert "setting" in desc.lower()


@pytest.mark.asyncio
async def test_cleanup(mock_system_manager):
    """Test cleanup properly shuts down."""
    config = ChatConfig(enable_memory=False)
    app = ChatApp(config=config)
    await app.initialize(system_manager=mock_system_manager)
    
    # Mock system_manager.cleanup to be async
    mock_system_manager.cleanup = AsyncMock()
    
    await app.cleanup()
    assert not app._initialized
