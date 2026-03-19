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

class InteractionEmbeddingManager:
    """Manages embeddings for complete chat interactions."""
    
    def __init__(self, llm_client, memory_store, schema_validator):
        """
        Initialize manager with required components.
        
        Args:
            llm_client: Ollama client instance
            memory_store: Memory storage instance
            schema_validator: Schema validator instance
        """
        self.client = llm_client
        self.store = memory_store
        self.validator = schema_validator
        self.logger = logging.getLogger(__name__)
    
    async def process_interaction(
        self,
        user_input: str,
        model_response: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Process and embed a complete interaction.
        
        Args:
            user_input: User's query/input
            model_response: Model's response
            metadata: Optional additional metadata
            
        Returns:
            str: Memory ID of stored interaction
        """
        try:
            # Combine interaction into a single context
            interaction_text = self._format_interaction(user_input, model_response)
            
            # Generate embedding for complete interaction
            embedding = await self.client.generate_embedding(interaction_text)
            
            # Prepare metadata
            full_metadata = self._prepare_metadata(user_input, model_response, metadata)
            
            # Validate embedding data
            await self._validate_embedding_data(interaction_text, embedding, full_metadata)
            
            # Store in memory system
            memory_id = await self.store.store_memory(
                content=interaction_text,
                metadata={
                    **full_metadata,
                    'embedding': embedding
                }
            )
            
            self.logger.info(f"Stored interaction with memory ID: {memory_id}")
            return memory_id
            
        except Exception as e:
            self.logger.error(f"Failed to process interaction: {str(e)}")
            raise
    
    async def retrieve_context(
        self,
        query: str,
        limit: int = 5,
        min_relevance: float = 0.7
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: Query to find relevant context for
            limit: Maximum number of relevant memories to retrieve
            min_relevance: Minimum relevance score threshold
            
        Returns:
            Tuple[List[Dict[str, Any]], str]: (relevant_memories, summarized_context)
        """
        try:
            # Get query embedding
            query_embedding = await self.client.generate_embedding(query)
            
            # Find relevant memories
            relevant_memories = await self.store.search(
                query,
                limit=limit,
                min_relevance=min_relevance
            )
            
            if not relevant_memories:
                return [], ""
            
            # Prepare context for summarization
            context_text = self._prepare_context_for_summarization(relevant_memories)
            
            # Get context summary using appropriate model
            summary = await self._get_context_summary(context_text)
            
            return relevant_memories, summary
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve context: {str(e)}")
            raise
    
    def _format_interaction(self, user_input: str, model_response: str) -> str:
        """Format a complete interaction for embedding."""
        return f"""User Input: {user_input}
Model Response: {model_response}
Timestamp: {datetime.now().isoformat()}"""
    
    def _prepare_metadata(
        self,
        user_input: str,
        model_response: str,
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Prepare metadata for interaction storage."""
        metadata = {
            'timestamp': datetime.now().isoformat(),
            'interaction_type': 'chat',
            'content_length': len(user_input) + len(model_response),
            'user_input_length': len(user_input),
            'response_length': len(model_response)
        }
        
        # Add analysis metadata
        metadata.update({
            'contains_question': '?' in user_input,
            'contains_code': '```' in model_response,
            'interaction_keywords': self._extract_keywords(user_input + " " + model_response)
        })
        
        if extra_metadata:
            metadata.update(extra_metadata)
        
        return metadata
    
    async def _validate_embedding_data(
        self,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any]
    ) -> None:
        """
        Validate embedding data before storage.
        
        Args:
            content: Interaction content
            embedding: Generated embedding
            metadata: Prepared metadata
            
        Raises:
            ValidationError: If validation fails
        """
        if self.validator:
            embedding_data = {
                'content': content,
                'embedding': embedding,
                'metadata': metadata
            }
            
            is_valid, error = await self.validator.validate_embedding_data(embedding_data)
            if not is_valid:
                raise MemoryValidationError(f"Invalid embedding data: {error}")
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract key terms from text for metadata."""
        # Simple keyword extraction - enhance as needed
        common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
        words = text.lower().split()
        return list(set(word for word in words if word not in common_words))[:10]
    
    def _prepare_context_for_summarization(
        self,
        memories: List[Dict[str, Any]]
    ) -> str:
        """Prepare retrieved memories for summarization."""
        context_parts = []
        for memory in memories:
            context_parts.append(f"""Memory:
Content: {memory['content']}
Relevance: {memory.get('relevance_score', 0.0):.2f}
Timestamp: {memory.get('timestamp', '')}
---""")
        
        return "\n".join(context_parts)
    
    async def _get_context_summary(self, context_text: str) -> str:
        """
        Get a summary of context using appropriate model.
        
        Args:
            context_text: Context to summarize
            
        Returns:
            str: Summarized context
        """
        try:
            # Use long-context model for larger texts
            if len(context_text) > 1000:
                model = self.client.summarize_long_model
            else:
                model = self.client.summarize_short_model
            
            summary = await self.client.summarize_text(
                context_text,
                max_length=200  # Adjust as needed
            )
            
            return summary
        except Exception as e:
            self.logger.error(f"Failed to generate context summary: {str(e)}")
            return ""  # Return empty summary on error


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
        truncated = context[:max_chars] + "[Context truncated...]"
        return truncated
    
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
