"""
Enhanced memory management with complete interaction embeddings.
Handles embedding generation for both user queries and model responses.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging
import json

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
                raise ValueError(f"Invalid embedding data: {error}")
    
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


class MemoryContextManager:
    """Manages conversation context and memory retrieval."""
    
    def __init__(
        self,
        memory_store,
        preference_store,
        max_context_turns: int = 5,
        min_relevance_score: float = 0.6,
        max_context_tokens: int = 2048
    ):
        """
        Initialize context manager.
        
        Args:
            memory_store: Base memory store instance
            preference_store: Preference store
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
        self.conversation_turns: List[Dict[str, Any]] = []
    
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
    
    def _format_recent_turns(self) -> List[Dict[str, Any]]:
        """Format recent conversation turns."""
        # Return the last N turns based on max_context_turns
        return self.conversation_turns[-self.max_context_turns:] if self.conversation_turns else []
    
    def _format_relevant_memories(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format relevant memories for context inclusion."""
        formatted_memories = []
        
        for memory in memories:
            # Filter memories by relevance score
            if memory.get('relevance_score', 0) < self.min_relevance_score:
                continue
                
            formatted_memories.append({
                'content': memory.get('content', ''),
                'timestamp': memory.get('timestamp', ''),
                'relevance': memory.get('relevance_score', 0),
                'memory_id': memory.get('id', '')
            })
            
        return formatted_memories
    
    def _format_complete_context(self, context_data: Dict[str, Any]) -> str:
        """Format complete context from all components."""
        parts = [
            f"# Conversation Context ({datetime.now().isoformat()})",
            "## User Query",
            context_data['query'],
        ]
        
        # Add preferences if present
        if context_data['preferences']:
            parts.extend([
                "## User Preferences",
                json.dumps(context_data['preferences'], indent=2)
            ])
        
        # Add conversation history
        if context_data['conversation_history']:
            parts.extend([
                "## Recent Conversation",
                self._format_conversation_history(context_data['conversation_history'])
            ])
        
        # Add relevant memories
        if context_data['relevant_memories']:
            parts.extend([
                "## Relevant Past Interactions",
                self._format_memories_section(context_data['relevant_memories'])
            ])
        
        return "\n\n".join(parts)
    
    def _format_conversation_history(self, history: List[Dict[str, Any]]) -> str:
        """Format conversation history for context."""
        history_parts = []
        
        for turn in history:
            timestamp = turn.get('timestamp', '')
            history_parts.append(f"User ({timestamp}):\n{turn.get('user_input', '')}")
            history_parts.append(f"Assistant:\n{turn.get('assistant_response', '')}")
        
        return "\n\n".join(history_parts)
    
    def _format_memories_section(self, memories: List[Dict[str, Any]]) -> str:
        """Format memories section for context."""
        memory_parts = []
        
        for memory in memories:
            memory_parts.append(f"""Memory (Relevance: {memory.get('relevance', 0):.2f})
Timestamp: {memory.get('timestamp', '')}
Content:
{memory.get('content', '')}
---""")
        
        return "\n".join(memory_parts)
    
    async def add_conversation_turn(
        self,
        user_input: str,
        assistant_response: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add a turn to the current conversation.
        
        Args:
            user_input: User's input
            assistant_response: Assistant's response
            metadata: Optional metadata about the turn
        """
        # Initialize conversation if not started
        if not self.current_conversation_id:
            self.current_conversation_id = f"conv-{datetime.now().timestamp()}"
            self.conversation_start_time = datetime.now().isoformat()
        
        # Create turn data
        turn_data = {
            'timestamp': datetime.now().isoformat(),
            'user_input': user_input,
            'assistant_response': assistant_response,
            'conversation_id': self.current_conversation_id
        }
        
        if metadata:
            turn_data.update(metadata)
        
        # Add to conversation turns
        self.conversation_turns.append(turn_data)
        
        # Store in memory system
        await self.store.store_memory(
            content=f"User: {user_input}\nAssistant: {assistant_response}",
            metadata={
                'type': 'conversation',
                'conversation_id': self.current_conversation_id,
                'timestamp': turn_data['timestamp'],
                **turn_data
            }
        )
    
    async def end_conversation(self) -> str:
        """
        End the current conversation and reset state.
        
        Returns:
            str: Conversation ID of ended conversation
        """
        ended_id = self.current_conversation_id
        
        # Reset conversation state
        self.current_conversation_id = None
        self.conversation_start_time = None
        self.conversation_turns = []
        
        return ended_id
