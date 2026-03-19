"""
Memory context management for enhanced conversation tracking.
File: src/memory/interactions.py
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from src.memory.models import Memory, MemorySearchResult, ConversationTurn
from src.memory.exceptions import MemoryValidationError, StorageError
from src.preferences.store import PreferenceStore

logger = logging.getLogger(__name__)

class MemoryContextManager:
    """Manages conversation context and memory retrieval."""
    
    def __init__(
        self,
        memory_store,
        preference_store: PreferenceStore,
        max_context_turns: int = 5,
        min_relevance_score: float = 0.6,
        max_context_tokens: int = 2048
    ):
        """
        Initialize context manager.
        
        Args:
            memory_store: Memory storage instance
            preference_store: Preference storage instance
            max_context_turns: Maximum conversation turns to include
            min_relevance_score: Minimum relevance for included memories
            max_context_tokens: Maximum tokens for context
        """
        self.store = memory_store
        self.preference_store = preference_store
        self.max_context_turns = max_context_turns
        self.min_relevance_score = min_relevance_score
        self.max_context_tokens = max_context_tokens
        
        # Conversation tracking
        self.current_conversation_id: Optional[str] = None
        self.conversation_start_time: Optional[str] = None
        self.conversation_turns: List[ConversationTurn] = []
    
    async def start_conversation(self) -> str:
        """
        Start a new conversation.
        
        Returns:
            str: Conversation ID
        """
        from uuid import uuid4
        self.current_conversation_id = f"conv_{uuid4().hex[:12]}"
        self.conversation_start_time = datetime.now().isoformat()
        self.conversation_turns.clear()
        return self.current_conversation_id
    
    async def add_conversation_turn(
        self,
        content: str,
        role: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ConversationTurn:
        """
        Add a turn to the conversation.
        
        Args:
            content: Turn content
            role: Turn role (user/assistant)
            metadata: Optional additional metadata
            
        Returns:
            ConversationTurn: Created turn
        """
        turn = ConversationTurn(
            role=role,
            content=content,
            turn_id=f"turn_{len(self.conversation_turns)}",
            timestamp=datetime.now().isoformat(),
            metadata={
                "conversation_id": self.current_conversation_id,
                **(metadata or {})
            }
        )
        
        self.conversation_turns.append(turn)
        return turn
    
    async def get_conversation_context(
        self,
        query: str,
        include_preferences: bool = True
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Get relevant context for the current conversation.
        
        Args:
            query: Query to find relevant context
            include_preferences: Whether to include preferences
            
        Returns:
            Tuple[str, Dict[str, Any]]: (formatted context, context data)
        """
        try:
            # Get relevant memories
            memories = await self.store.search(
                query,
                limit=self.max_context_turns,
                metadata_filter={"type": "conversation"}
            )
            
            # Prepare context data
            context_data = {
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "preferences": {},
                "conversation_history": self._format_recent_turns(),
                "relevant_memories": self._format_relevant_memories(memories)
            }
            
            # Add preferences if requested
            if include_preferences:
                context_data["preferences"] = await self.preference_store.get_all_preferences()
            
            # Format complete context
            formatted_context = self._format_complete_context(context_data)
            
            return formatted_context, context_data
            
        except Exception as e:
            logger.error(f"Failed to get conversation context: {str(e)}")
            raise StorageError(f"Failed to get conversation context: {str(e)}")
    
    def _format_recent_turns(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Format recent conversation turns."""
        if limit is None:
            limit = self.max_context_turns
            
        recent_turns = self.conversation_turns[-limit:]
        return [
            {
                "role": turn.role,
                "content": turn.content,
                "timestamp": turn.timestamp,
                "turn_id": turn.turn_id
            }
            for turn in recent_turns
        ]
    
    def _format_relevant_memories(
        self,
        memories: List[MemorySearchResult]
    ) -> List[Dict[str, Any]]:
        """Format relevant memories for context."""
        relevant = []
        
        for memory in memories:
            if memory.relevance_score < self.min_relevance_score:
                continue
                
            relevant.append({
                "content": memory.content,
                "relevance": memory.relevance_score,
                "timestamp": memory.timestamp,
                "type": memory.metadata.get("type", "unknown")
            })
            
        return relevant
    
    def _format_complete_context(self, context_data: Dict[str, Any]) -> str:
        """Format complete context string."""
        context_parts = []
        
        # Add conversation history
        if context_data["conversation_history"]:
            context_parts.append("Previous conversation:")
            for turn in context_data["conversation_history"]:
                timestamp = datetime.fromisoformat(turn["timestamp"]).strftime("%H:%M:%S")
                role = turn["role"].capitalize()
                context_parts.append(f"[{timestamp}] {role}: {turn['content']}")
            context_parts.append("")
        
        # Add relevant memories
        if context_data["relevant_memories"]:
            context_parts.append("Related information:")
            for memory in context_data["relevant_memories"]:
                timestamp = datetime.fromisoformat(memory["timestamp"]).strftime("%Y-%m-%d")
                context_parts.append(
                    f"[{timestamp}] {memory['content']} "
                    f"(Relevance: {memory['relevance']:.2f})"
                )
            context_parts.append("")
        
        # Add preferences
        preferences = context_data.get("preferences", {})
        if preferences:
            context_parts.append("User preferences:")
            for pref_type, pref_data in preferences.items():
                if isinstance(pref_data, dict) and "value" in pref_data:
                    context_parts.append(f"- {pref_type}: {pref_data['value']}")
            context_parts.append("")
        
        # Join all parts and truncate if needed
        context = "\n".join(context_parts)
        return self._truncate_context(context)
    
    def _truncate_context(
        self,
        context: str,
        chars_per_token: float = 4.0
    ) -> str:
        """Truncate context to fit token limit."""
        max_chars = int(self.max_context_tokens * chars_per_token)
        
        if len(context) <= max_chars:
            return context
        
        # Try to truncate at paragraph
        truncated = context[:max_chars]
        last_para = truncated.rfind('\n\n')
        if last_para > 0:
            return context[:last_para] + "\n\n[Context truncated...]"
        
        # Try to truncate at sentence
        last_sent = truncated.rfind('. ')
        if last_sent > 0:
            return context[:last_sent + 1] + " [Context truncated...]"
        
        # Last resort: hard truncate
        return truncated + "[Context truncated...]"
    
    async def get_conversation_summary(self) -> Dict[str, Any]:
        """
        Get summary of current conversation.
        
        Returns:
            Dict[str, Any]: Conversation summary
        """
        if not self.current_conversation_id:
            return {}
            
        return {
            "conversation_id": self.current_conversation_id,
            "start_time": self.conversation_start_time,
            "turn_count": len(self.conversation_turns),
            "duration_seconds": (
                datetime.now() - 
                datetime.fromisoformat(self.conversation_start_time)
            ).total_seconds(),
            "roles": {
                role: sum(1 for turn in self.conversation_turns if turn.role == role)
                for role in {'user', 'assistant'}
            }
        }
    
    async def end_conversation(self) -> None:
        """End current conversation and clean up."""
        self.current_conversation_id = None
        self.conversation_start_time = None
        self.conversation_turns.clear()
