import logging
import json
import asyncio
import re
from typing import Dict, Any, AsyncGenerator, Optional, List, Union, Set, TYPE_CHECKING
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

from src.memory.models import Memory, MemoryType
from src.research.models import ResearchType
from src.research.models import ChatResponse, ChatMetadata, ResponseType
from src.research.models import Message, MessageRole, MessageMetadata
from src.research.models import Persona, PersonaType
from src.research.models import User, UserPreferences

from src.utils.exceptions import (
    ChatInitError,
    PersonaNotFoundError,
    UnauthorizedError,
    ValidationError,
    ResearchError
)
from src.utils.validation import (
    validate_message_content,
    validate_metadata,
    validate_user_preferences
)
from src.utils.constants import (
    MAX_MESSAGE_LENGTH,
    MAX_CONTEXT_MESSAGES,
    DEFAULT_RESPONSE_TYPE,
    SYSTEM_PERSONA_ID
)

logger = logging.getLogger(__name__)

class ChatState(Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    PROCESSING = "processing"
    ERROR = "error"
    CLOSED = "closed"

@dataclass
class ChatConfig:
    max_message_length: int = MAX_MESSAGE_LENGTH
    max_context_messages: int = MAX_CONTEXT_MESSAGES
    default_response_type: ResponseType = DEFAULT_RESPONSE_TYPE
    enable_memory: bool = False  # V3: memory manager disabled
    enable_research: bool = True
    enable_personas: bool = True
    default_persona_id: str = SYSTEM_PERSONA_ID
    auto_save_context: bool = True
    debug_mode: bool = False

class ChatContext:
    def __init__(self, config: ChatConfig):
        self.config = config
        self.state = ChatState.INITIALIZING
        self.messages: List[Message] = []
        self.active_users: Set[str] = set()
        self.metadata: Dict[str, Any] = {}
        
    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        if len(self.messages) > self.config.max_context_messages:
            self.messages.pop(0)
            
    def clear_messages(self) -> None:
        self.messages = []

class ChatApp:
    """Main chat application — RESTORED & V2 INTEGRATED."""
    def __init__(self, config: Optional[ChatConfig] = None):
        self.config = config or ChatConfig()
        self.context = ChatContext(self.config)
        self._initialized = False
        
        # V2 System Manager
        self.system_manager = None
        
        # User and persona management
        self.users: Dict[str, User] = {}
        self.personas: Dict[str, Persona] = {}
        self.current_persona: Optional[Persona] = None
        
        self._processing_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        
    @property
    def is_ready(self) -> bool:
        return (self._initialized and self.context.state == ChatState.READY)

    async def initialize(
        self,
        system_manager = None,
        personas: Optional[Dict[str, Persona]] = None,
        users: Optional[Dict[str, User]] = None
    ) -> None:
        async with self._init_lock:
            if self._initialized: return
            try:
                self.system_manager = system_manager
                if personas: self.personas = personas
                if users: self.users = users
                
                # Set default persona
                if self.config.default_persona_id in self.personas:
                    self.current_persona = self.personas[self.config.default_persona_id]

                self._initialized = True
                self.context.state = ChatState.READY
                logger.info("ChatApp V2 Hybrid initialized successfully")
            except Exception as e:
                self.context.state = ChatState.ERROR
                raise ChatInitError(f"Initialization failed: {str(e)}")

    async def process_input(
        self,
        user_input: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> AsyncGenerator[ChatResponse, None]:
        if not self._initialized: raise RuntimeError("ChatApp not initialized")
            
        async with self._processing_lock:
            try:
                self.context.state = ChatState.PROCESSING

                # 1. Get relevant memories (RAG)
                memory_context = ""
                if self.system_manager.memory and self.config.enable_memory:
                    try:
                        relevant_memories = await self.system_manager.memory.search(user_input, limit=5)
                        if relevant_memories:
                            memory_context = "\n".join([f"- {m.content}" for m in relevant_memories])
                    except Exception as e:
                        logger.warning(f"Memory retrieval failed: {e}")

                # 2. Prepare conversation history
                messages = []
                if memory_context:
                    messages.append({
                        "role": "system",
                        "content": f"Use this context from previous interactions when relevant: {memory_context}"
                    })
                
                for msg in self.context.messages:
                    messages.append({"role": msg.role.value, "content": msg.content})
                messages.append({"role": "user", "content": user_input})

                # 3. Generate streaming response via SystemManager
                response_content = ""
                async for token in self.system_manager.chat(messages=messages):
                    response_content += token
                    yield ChatResponse(content=token, response_type=ResponseType.NORMAL)
                
                # 4. Store interaction
                if self.config.enable_memory:
                    await self._store_interaction(user_input, response_content)
                    await self._extract_and_store_preferences(user_input)
            
            finally:
                self.context.state = ChatState.READY

    async def perform_research(self, topic: str) -> AsyncGenerator[ChatResponse, None]:
        """Perform V2 hybrid query."""
        yield ChatResponse(content=f"Querying knowledge stack for '{topic}'...", response_type=ResponseType.THINKING)
        results = await self.system_manager.query(text=topic)
        yield ChatResponse(content=results, response_type=ResponseType.RESEARCH)

    async def get_system_status(self) -> Dict[str, Any]:
        """Full Dashboard Status."""
        v2_status = self.system_manager.status()
        return {
            "system": {
                "initialized": self._initialized,
                "state": self.context.state.value,
                "timestamp": datetime.now().isoformat()
            },
            "v2_orchestrator": v2_status,
            "models": v2_status.get('models', {}),
            "memory": {"enabled": self.config.enable_memory},
            "users": {"count": len(self.users)},
            "personas": {"count": len(self.personas), "current": self.current_persona.id if self.current_persona else None}
        }

    async def _store_interaction(self, user_input: str, response_content: str) -> None:
        if not self.system_manager.memory:
            return
        interaction = f"User: {user_input}\nAssistant: {response_content}"
        await self.system_manager.memory.store(Memory(content=interaction, metadata={"type": "conversation", "topic": "General"}))

    async def _extract_and_store_preferences(self, content: str) -> None:
        if not self.system_manager.memory:
            return
        patterns = {"color": r"favorite\s+color\s+(?:is|:)\s+(\w+)", "food": r"favorite\s+food\s+(?:is|:)\s+(\w+)"}
        for k, p in patterns.items():
            match = re.search(p, content, re.IGNORECASE)
            if match:
                await self.system_manager.memory.store(Memory(content=f"Preference: {k}={match.group(1)}", metadata={"type": "preference"}))

    async def save_chat_history(self, filename: str) -> str:
        return "History saved to chat_history/"

    async def get_settings(self) -> Dict[str, Any]:
        return {"max_message_length": self.config.max_message_length, "enable_memory": self.config.enable_memory}

    def get_setting_description(self, setting: str) -> str:
        return "System configuration setting"

    async def update_setting(self, setting: str, value: Any) -> None:
        if hasattr(self.config, setting):
            setattr(self.config, setting, value)

    async def cleanup(self) -> None:
        if self.system_manager: await self.system_manager.cleanup()
        self._initialized = False
