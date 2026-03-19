"""
Memory models for persistent memory management.
File: src/memory/models.py
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Union, Set
from enum import Enum

class MemoryType(str, Enum):
    """Types of memory entries."""
    CONVERSATION = "conversation"
    RESEARCH = "research"
    PREFERENCE = "preference"
    CONTEXT = "context"
    KNOWLEDGE = "knowledge"
    TASK = "task"

def sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize metadata to ensure it's compatible with storage backends."""
    sanitized = {}
    for key, value in metadata.items():
        # Convert lists and dicts to strings
        if isinstance(value, (list, dict)):
            sanitized[key] = str(value)
        # Only store simple types
        elif isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
        # Skip other types
        else:
            continue
    return sanitized

@dataclass
class Memory:
    """Core memory model for storing and retrieving embeddings."""
    content: str
    embedding_id: str = field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:12]}")
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __init__(self, content, metadata=None, embedding=None, embedding_id=None):
        # Ensure content is a string
        if isinstance(content, list):
            self.content = "\n\n".join(str(item) for item in content)
        elif not isinstance(content, str):
            self.content = str(content)
        else:
            self.content = content
            
        self.metadata = metadata or {}
        self.embedding = embedding
        self.embedding_id = embedding_id or f"mem_{uuid.uuid4().hex[:12]}"
    
    def __post_init__(self):
        """Validate memory after initialization."""
        # This is kept for backwards compatibility
        # Validate content is a string - already handled in __init__, but keep as a safeguard
        if not isinstance(self.content, str):
            if isinstance(self.content, list):
                self.content = '\n'.join(str(item) for item in self.content)
            else:
                self.content = str(self.content)
                
        if not self.content:
            raise ValueError("Memory content cannot be empty")
        
        # Ensure metadata has a timestamp
        if 'timestamp' not in self.metadata:
            self.metadata['timestamp'] = datetime.now().isoformat()
        
        # Ensure metadata has a type
        if 'type' not in self.metadata:
            self.metadata['type'] = 'general'
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert memory to dictionary."""
        return {
            'embedding_id': self.embedding_id,
            'content': self.content,
            'embedding': self.embedding,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Memory':
        """Create memory from dictionary."""
        return cls(
            content=data['content'],
            embedding_id=data.get('embedding_id', f"mem_{uuid.uuid4().hex[:12]}"),
            embedding=data.get('embedding'),
            metadata=data.get('metadata', {})
        )

@dataclass
class MemoryChunk:
    """Chunk of a larger memory for efficient storage and retrieval."""
    content: str
    parent_id: str
    chunk_id: str = field(default_factory=lambda: f"chunk_{uuid.uuid4().hex[:8]}")
    embedding: Optional[List[float]] = None
    start_idx: int = 0
    end_idx: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate memory chunk after initialization."""
        if not self.content:
            raise ValueError("Chunk content cannot be empty")
        if not self.parent_id:
            raise ValueError("Parent ID cannot be empty")
            
        # Set chunk length in metadata
        self.metadata['chunk_length'] = len(self.content)
        
        # Ensure metadata has a timestamp
        if 'timestamp' not in self.metadata:
            self.metadata['timestamp'] = datetime.now().isoformat()
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary."""
        return {
            'chunk_id': self.chunk_id,
            'parent_id': self.parent_id,
            'content': self.content,
            'embedding': self.embedding,
            'start_idx': self.start_idx,
            'end_idx': self.end_idx,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryChunk':
        """Create chunk from dictionary."""
        return cls(
            content=data['content'],
            parent_id=data['parent_id'],
            chunk_id=data.get('chunk_id', f"chunk_{uuid.uuid4().hex[:8]}"),
            embedding=data.get('embedding'),
            start_idx=data.get('start_idx', 0),
            end_idx=data.get('end_idx', 0),
            metadata=data.get('metadata', {})
        )

@dataclass
class MemorySearchResult:
    """Result of a memory search operation."""
    content: str
    embedding_id: str
    relevance_score: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    
    def __post_init__(self):
        """Validate search result after initialization."""
        if not self.content:
            raise ValueError("Result content cannot be empty")
        if not self.embedding_id:
            raise ValueError("Embedding ID cannot be empty")
        if not (0 <= self.relevance_score <= 1):
            raise ValueError("Relevance score must be between 0 and 1")
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert search result to dictionary."""
        return {
            'content': self.content,
            'embedding_id': self.embedding_id,
            'relevance_score': self.relevance_score,
            'timestamp': self.timestamp,
            'metadata': self.metadata,
            'embedding': self.embedding
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemorySearchResult':
        """Create search result from dictionary."""
        return cls(
            content=data['content'],
            embedding_id=data['embedding_id'],
            relevance_score=data.get('relevance_score', 0.0),
            timestamp=data.get('timestamp', datetime.now().isoformat()),
            metadata=data.get('metadata', {}),
            embedding=data.get('embedding')
        )
        
@dataclass
class ConversationTurn:
    """Model for a single conversation turn."""
    role: str  # 'user' or 'assistant'
    content: str
    turn_id: str = field(default_factory=lambda: f"turn_{uuid.uuid4().hex[:8]}")
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate conversation turn after initialization."""
        if not self.role:
            raise ValueError("Role cannot be empty")
        if self.role not in {'user', 'assistant', 'system'}:
            raise ValueError(f"Invalid role: {self.role}")
        if not self.content:
            raise ValueError("Content cannot be empty")
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert conversation turn to dictionary."""
        return {
            'role': self.role,
            'content': self.content,
            'turn_id': self.turn_id,
            'timestamp': self.timestamp,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationTurn':
        """Create conversation turn from dictionary."""
        return cls(
            role=data['role'],
            content=data['content'],
            turn_id=data.get('turn_id', f"turn_{uuid.uuid4().hex[:8]}"),
            timestamp=data.get('timestamp', datetime.now().isoformat()),
            metadata=data.get('metadata', {})
        )

@dataclass
class Conversation:
    """Model for a complete conversation."""
    conversation_id: str
    turns: List[ConversationTurn] = field(default_factory=list)
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    
    def __post_init__(self):
        """Validate conversation after initialization."""
        if not self.conversation_id:
            raise ValueError("Conversation ID cannot be empty")
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def add_turn(self, turn: ConversationTurn) -> None:
        """Add a turn to the conversation."""
        self.turns.append(turn)
        
        # Update conversation's metadata with turn count
        self.metadata['turn_count'] = len(self.turns)
        # Ensure metadata is sanitized after updates
        self.metadata = sanitize_metadata(self.metadata)
    
    def end(self) -> None:
        """End the conversation."""
        self.end_time = datetime.now().isoformat()
        
        # Update duration in metadata
        start = datetime.fromisoformat(self.start_time)
        end = datetime.fromisoformat(self.end_time)
        self.metadata['duration_seconds'] = (end - start).total_seconds()
        # Ensure metadata is sanitized after updates
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert conversation to dictionary."""
        return {
            'conversation_id': self.conversation_id,
            'turns': [turn.to_dict() for turn in self.turns],
            'start_time': self.start_time,
            'end_time': self.end_time,
            'metadata': self.metadata,
            'embedding': self.embedding
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Conversation':
        """Create conversation from dictionary."""
        conversation = cls(
            conversation_id=data['conversation_id'],
            start_time=data.get('start_time', datetime.now().isoformat()),
            end_time=data.get('end_time'),
            metadata=data.get('metadata', {}),
            embedding=data.get('embedding')
        )
        
        # Add turns if present
        if 'turns' in data:
            for turn_data in data['turns']:
                conversation.turns.append(ConversationTurn.from_dict(turn_data))
        
        return conversation

@dataclass
class MemoryContext:
    """Context assembled from relevant memories."""
    query: str
    memories: List[MemorySearchResult] = field(default_factory=list)
    conversation_history: List[ConversationTurn] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    context_id: str = field(default_factory=lambda: f"ctx_{uuid.uuid4().hex[:8]}")
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate memory context after initialization."""
        if not self.query:
            raise ValueError("Query cannot be empty")
            
        # Sanitize metadata and preferences
        self.metadata = sanitize_metadata(self.metadata)
        self.preferences = sanitize_metadata(self.preferences)
    
    def add_memory(self, memory: MemorySearchResult) -> None:
        """Add a memory to the context."""
        self.memories.append(memory)
    
    def add_conversation_turn(self, turn: ConversationTurn) -> None:
        """Add a conversation turn to the context."""
        self.conversation_history.append(turn)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert memory context to dictionary."""
        return {
            'query': self.query,
            'memories': [m.to_dict() for m in self.memories],
            'conversation_history': [t.to_dict() for t in self.conversation_history],
            'preferences': self.preferences,
            'timestamp': self.timestamp,
            'context_id': self.context_id,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryContext':
        """Create memory context from dictionary."""
        context = cls(
            query=data['query'],
            timestamp=data.get('timestamp', datetime.now().isoformat()),
            context_id=data.get('context_id', f"ctx_{uuid.uuid4().hex[:8]}"),
            preferences=data.get('preferences', {}),
            metadata=data.get('metadata', {})
        )
        
        # Add memories if present
        if 'memories' in data:
            for memory_data in data['memories']:
                context.memories.append(MemorySearchResult.from_dict(memory_data))
        
        # Add conversation turns if present
        if 'conversation_history' in data:
            for turn_data in data['conversation_history']:
                context.conversation_history.append(ConversationTurn.from_dict(turn_data))
        
        return context

@dataclass
class MemoryConfig:
    """Configuration for memory operations."""
    embedding_dimension: int = 1024
    embedding_batch_size: int = 16
    max_retries: int = 3
    retry_delay: float = 1.0
    chunk_size: int = 1000
    chunk_overlap: int = 100
    min_relevance_score: float = 0.6
    max_context_items: int = 5
    max_conversation_turns: int = 10
    
    def __post_init__(self):
        """Validate memory configuration."""
        if self.embedding_dimension <= 0:
            raise ValueError("Embedding dimension must be positive")
        if self.embedding_batch_size <= 0:
            raise ValueError("Embedding batch size must be positive")
        if self.max_retries < 0:
            raise ValueError("Max retries must be non-negative")
        if self.retry_delay < 0:
            raise ValueError("Retry delay must be non-negative")
        if self.chunk_size <= 0:
            raise ValueError("Chunk size must be positive")
        if self.chunk_overlap < 0:
            raise ValueError("Chunk overlap must be non-negative")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be less than chunk size")
        if not (0 <= self.min_relevance_score <= 1):
            raise ValueError("Min relevance score must be between 0 and 1")
        if self.max_context_items <= 0:
            raise ValueError("Max context items must be positive")
        if self.max_conversation_turns <= 0:
            raise ValueError("Max conversation turns must be positive")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'embedding_dimension': self.embedding_dimension,
            'embedding_batch_size': self.embedding_batch_size,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'min_relevance_score': self.min_relevance_score,
            'max_context_items': self.max_context_items,
            'max_conversation_turns': self.max_conversation_turns
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryConfig':
        """Create configuration from dictionary."""
        return cls(**data)

@dataclass
class PreferenceItem:
    """Model for user preferences."""
    key: str
    value: Any
    category: str = "general"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate preference item after initialization."""
        if not self.key:
            raise ValueError("Preference key cannot be empty")
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
        
        # Sanitize value if it's complex
        if isinstance(self.value, (list, dict)):
            self.value = str(self.value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert preference item to dictionary."""
        return {
            'key': self.key,
            'value': self.value,
            'category': self.category,
            'timestamp': self.timestamp,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PreferenceItem':
        """Create preference item from dictionary."""
        return cls(
            key=data['key'],
            value=data['value'],
            category=data.get('category', 'general'),
            timestamp=data.get('timestamp', datetime.now().isoformat()),
            metadata=data.get('metadata', {})
        )

@dataclass
class LongTermMemory:
    """Model for long-term memories with permanence settings."""
    content: str
    importance: float = 0.5  # 0.0 to 1.0
    memory_id: str = field(default_factory=lambda: f"ltm_{uuid.uuid4().hex[:12]}")
    embedding: Optional[List[float]] = None
    create_time: str = field(default_factory=lambda: datetime.now().isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0
    decay_factor: float = 0.05  # How quickly memory fades if not accessed
    metadata: Dict[str, Any] = field(default_factory=dict)
    permanently_store: bool = False  # If true, never removed in cleanup
    
    def __post_init__(self):
        """Validate long-term memory after initialization."""
        if not self.content:
            raise ValueError("Memory content cannot be empty")
        if not (0 <= self.importance <= 1):
            raise ValueError("Importance must be between 0 and 1")
        if not (0 <= self.decay_factor <= 1):
            raise ValueError("Decay factor must be between 0 and 1")
        
        # Initialize memory type if not specified
        if 'type' not in self.metadata:
            self.metadata['type'] = 'long_term'
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def access(self) -> None:
        """Record an access to this memory."""
        self.last_accessed = datetime.now().isoformat()
        self.access_count += 1
    
    def calculate_retention_score(self) -> float:
        """
        Calculate retention score based on importance, access patterns, and decay.
        Higher scores mean the memory should be retained.
        """
        # Calculate time since last access
        current_time = datetime.now()
        last_access_time = datetime.fromisoformat(self.last_accessed)
        days_since_access = (current_time - last_access_time).total_seconds() / (24 * 3600)
        
        # Calculate time factor (decays with time)
        time_factor = max(0, 1 - (days_since_access * self.decay_factor))
        
        # Calculate access factor (increases with more accesses)
        access_factor = min(1, self.access_count / 10)  # Caps at 10 accesses
        
        # Calculate retention score
        retention_score = (
            (self.importance * 0.6) +  # Importance is the main factor
            (time_factor * 0.3) +      # Recency of access
            (access_factor * 0.1)      # Frequency of access
        )
        
        return retention_score
    
    def should_retain(self, threshold: float = 0.3) -> bool:
        """Determine if memory should be retained based on retention score."""
        if self.permanently_store:
            return True
        
        return self.calculate_retention_score() >= threshold
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert long-term memory to dictionary."""
        return {
            'memory_id': self.memory_id,
            'content': self.content,
            'importance': self.importance,
            'embedding': self.embedding,
            'create_time': self.create_time,
            'last_accessed': self.last_accessed,
            'access_count': self.access_count,
            'decay_factor': self.decay_factor,
            'metadata': self.metadata,
            'permanently_store': self.permanently_store,
            'retention_score': self.calculate_retention_score()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LongTermMemory':
        """Create long-term memory from dictionary."""
        return cls(
            content=data['content'],
            importance=data.get('importance', 0.5),
            memory_id=data.get('memory_id', f"ltm_{uuid.uuid4().hex[:12]}"),
            embedding=data.get('embedding'),
            create_time=data.get('create_time', datetime.now().isoformat()),
            last_accessed=data.get('last_accessed', datetime.now().isoformat()),
            access_count=data.get('access_count', 0),
            decay_factor=data.get('decay_factor', 0.05),
            metadata=data.get('metadata', {}),
            permanently_store=data.get('permanently_store', False)
        )
        
@dataclass
class MemoryStoreStats:
    """Statistics for memory store performance."""
    store_type: str
    total_memories: int = 0
    total_embeddings: int = 0
    retrieval_count: int = 0
    storage_count: int = 0
    search_count: int = 0
    average_search_time: float = 0.0
    average_storage_time: float = 0.0
    average_retrieval_time: float = 0.0
    error_count: int = 0
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def update_search(self, duration: float) -> None:
        """Update search statistics."""
        self.search_count += 1
        self.average_search_time = (
            (self.average_search_time * (self.search_count - 1) + duration) / 
            self.search_count
        )
        self.last_updated = datetime.now().isoformat()
    
    def update_storage(self, duration: float) -> None:
        """Update storage statistics."""
        self.storage_count += 1
        self.total_memories += 1
        self.average_storage_time = (
            (self.average_storage_time * (self.storage_count - 1) + duration) / 
            self.storage_count
        )
        self.last_updated = datetime.now().isoformat()
    
    def update_retrieval(self, duration: float) -> None:
        """Update retrieval statistics."""
        self.retrieval_count += 1
        self.average_retrieval_time = (
            (self.average_retrieval_time * (self.retrieval_count - 1) + duration) / 
            self.retrieval_count
        )
        self.last_updated = datetime.now().isoformat()
    
    def record_error(self) -> None:
        """Record an error."""
        self.error_count += 1
        self.last_updated = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert statistics to dictionary."""
        return {
            'store_type': self.store_type,
            'total_memories': self.total_memories,
            'total_embeddings': self.total_embeddings,
            'retrieval_count': self.retrieval_count,
            'storage_count': self.storage_count,
            'search_count': self.search_count,
            'average_search_time': self.average_search_time,
            'average_storage_time': self.average_storage_time,
            'average_retrieval_time': self.average_retrieval_time,
            'error_count': self.error_count,
            'last_updated': self.last_updated
        }

@dataclass
class EmbeddingInfo:
    """Information about embeddings for a memory."""
    memory_id: str
    model: str
    dimension: int
    normalized: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate embedding info after initialization."""
        if not self.memory_id:
            raise ValueError("Memory ID cannot be empty")
        if not self.model:
            raise ValueError("Model name cannot be empty")
        if self.dimension <= 0:
            raise ValueError("Dimension must be positive")
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert embedding info to dictionary."""
        return {
            'memory_id': self.memory_id,
            'model': self.model,
            'dimension': self.dimension,
            'normalized': self.normalized,
            'timestamp': self.timestamp,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmbeddingInfo':
        """Create embedding info from dictionary."""
        return cls(
            memory_id=data['memory_id'],
            model=data['model'],
            dimension=data['dimension'],
            normalized=data.get('normalized', True),
            timestamp=data.get('timestamp', datetime.now().isoformat()),
            metadata=data.get('metadata', {})
        )

@dataclass
class EmbeddingRequest:
    """Request for embedding generation."""
    content: str
    model: str = "mxbai-embed-large"
    task_id: str = field(default_factory=lambda: f"emb_req_{uuid.uuid4().hex[:8]}")
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate embedding request after initialization."""
        if not self.content:
            raise ValueError("Content cannot be empty")
        if not self.model:
            raise ValueError("Model name cannot be empty")
        
        # Set request timestamp
        self.metadata['request_timestamp'] = datetime.now().isoformat()
        
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert embedding request to dictionary."""
        return {
            'content': self.content,
            'model': self.model,
            'task_id': self.task_id,
            'metadata': self.metadata
        }

@dataclass
class EmbeddingResponse:
    """Response from embedding generation."""
    embedding: List[float]
    task_id: str
    model: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate embedding response after initialization."""
        if not self.embedding:
            raise ValueError("Embedding cannot be empty")
        if not self.task_id:
            raise ValueError("Task ID cannot be empty")
        if not self.model:
            raise ValueError("Model name cannot be empty")
        
        # Set response timestamp
        self.metadata['response_timestamp'] = datetime.now().isoformat()
        
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert embedding response to dictionary."""
        return {
            'embedding': self.embedding,
            'task_id': self.task_id,
            'model': self.model,
            'metadata': self.metadata
        }

# Memory cache configuration and models
@dataclass
class MemoryCacheItem:
    """Item stored in memory cache."""
    key: str
    value: Any
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    expiry: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate cache item after initialization."""
        if not self.key:
            raise ValueError("Cache key cannot be empty")
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
        
        # Sanitize value if it's complex
        if isinstance(self.value, (list, dict)):
            self.value = str(self.value)
    
    def is_expired(self) -> bool:
        """Check if cache item is expired."""
        if not self.expiry:
            return False
        
        expiry_time = datetime.fromisoformat(self.expiry)
        current_time = datetime.now()
        return current_time > expiry_time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert cache item to dictionary."""
        return {
            'key': self.key,
            'value': self.value,
            'timestamp': self.timestamp,
            'expiry': self.expiry,
            'metadata': self.metadata,
            'is_expired': self.is_expired()
        }
    

@dataclass
class MemoryCacheConfig:
    """Configuration for memory cache."""
    max_size: int = 1000
    ttl_seconds: int = 3600  # 1 hour
    eviction_policy: str = "lru"  # Options: "lru", "fifo", "random"
    cache_embeddings: bool = True
    
    def __post_init__(self):
        """Validate cache configuration."""
        if self.max_size <= 0:
            raise ValueError("Max size must be positive")
        if self.ttl_seconds < 0:
            raise ValueError("TTL must be non-negative")
        
        valid_policies = {"lru", "fifo", "random"}
        if self.eviction_policy not in valid_policies:
            raise ValueError(f"Eviction policy must be one of: {', '.join(valid_policies)}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert cache configuration to dictionary."""
        return {
            'max_size': self.max_size,
            'ttl_seconds': self.ttl_seconds,
            'eviction_policy': self.eviction_policy,
            'cache_embeddings': self.cache_embeddings
        }

@dataclass
class MemoryCacheStats:
    """Statistics for memory cache."""
    hits: int = 0
    misses: int = 0
    insertions: int = 0
    evictions: int = 0
    size: int = 0
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def record_hit(self) -> None:
        """Record a cache hit."""
        self.hits += 1
        self.last_updated = datetime.now().isoformat()
    
    def record_miss(self) -> None:
        """Record a cache miss."""
        self.misses += 1
        self.last_updated = datetime.now().isoformat()
    
    def record_insertion(self) -> None:
        """Record a cache insertion."""
        self.insertions += 1
        self.size += 1
        self.last_updated = datetime.now().isoformat()
    
    def record_eviction(self) -> None:
        """Record a cache eviction."""
        self.evictions += 1
        self.size -= 1
        self.last_updated = datetime.now().isoformat()
    
    def hit_rate(self) -> float:
        """Calculate hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert cache statistics to dictionary."""
        return {
            'hits': self.hits,
            'misses': self.misses,
            'insertions': self.insertions,
            'evictions': self.evictions,
            'size': self.size,
            'hit_rate': self.hit_rate(),
            'last_updated': self.last_updated
        }

# Special memory types for different purposes
@dataclass
class KeyMemory:
    """Important memory that should be prioritized in context."""
    content: str
    key: str
    importance: float = 1.0  # Always high for key memories
    embedding_id: str = field(default_factory=lambda: f"key_{uuid.uuid4().hex[:12]}")
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate key memory after initialization."""
        if not self.content:
            raise ValueError("Memory content cannot be empty")
        if not self.key:
            raise ValueError("Key cannot be empty")
        
        # Set memory type in metadata
        self.metadata['type'] = 'key_memory'
        self.metadata['importance'] = self.importance
        
        # Ensure metadata has a timestamp
        if 'timestamp' not in self.metadata:
            self.metadata['timestamp'] = datetime.now().isoformat()
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert key memory to dictionary."""
        return {
            'key': self.key,
            'content': self.content,
            'importance': self.importance,
            'embedding_id': self.embedding_id,
            'embedding': self.embedding,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KeyMemory':
        """Create key memory from dictionary."""
        return cls(
            content=data['content'],
            key=data['key'],
            importance=data.get('importance', 1.0),
            embedding_id=data.get('embedding_id', f"key_{uuid.uuid4().hex[:12]}"),
            embedding=data.get('embedding'),
            metadata=data.get('metadata', {})
        )
        
@dataclass
class FactMemory:
    """Memory representing a specific fact."""
    content: str
    fact_id: str = field(default_factory=lambda: f"fact_{uuid.uuid4().hex[:12]}")
    categories: List[str] = field(default_factory=list)
    confidence: float = 0.9
    verified: bool = False
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate fact memory after initialization."""
        if not self.content:
            raise ValueError("Fact content cannot be empty")
        if not (0 <= self.confidence <= 1):
            raise ValueError("Confidence must be between 0 and 1")
        
        # Set memory type in metadata
        self.metadata['type'] = 'fact'
        self.metadata['confidence'] = self.confidence
        self.metadata['verified'] = self.verified
        
        # Ensure metadata has a timestamp
        if 'timestamp' not in self.metadata:
            self.metadata['timestamp'] = datetime.now().isoformat()
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def verify(self, verification_source: Optional[str] = None) -> None:
        """Mark the fact as verified."""
        self.verified = True
        self.metadata['verified'] = True
        self.metadata['verification_source'] = verification_source
        self.metadata['verification_time'] = datetime.now().isoformat()
        # Ensure metadata is sanitized after updates
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert fact memory to dictionary."""
        return {
            'fact_id': self.fact_id,
            'content': self.content,
            'categories': self.categories,
            'confidence': self.confidence,
            'verified': self.verified,
            'embedding': self.embedding,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FactMemory':
        """Create fact memory from dictionary."""
        return cls(
            content=data['content'],
            fact_id=data.get('fact_id', f"fact_{uuid.uuid4().hex[:12]}"),
            categories=data.get('categories', []),
            confidence=data.get('confidence', 0.9),
            verified=data.get('verified', False),
            embedding=data.get('embedding'),
            metadata=data.get('metadata', {})
        )

@dataclass
class RelationMemory:
    """Memory representing a relationship between entities."""
    source_entity: str
    relation_type: str
    target_entity: str
    relation_id: str = field(default_factory=lambda: f"rel_{uuid.uuid4().hex[:12]}")
    confidence: float = 0.9
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate relation memory after initialization."""
        if not self.source_entity:
            raise ValueError("Source entity cannot be empty")
        if not self.relation_type:
            raise ValueError("Relation type cannot be empty")
        if not self.target_entity:
            raise ValueError("Target entity cannot be empty")
        if not (0 <= self.confidence <= 1):
            raise ValueError("Confidence must be between 0 and 1")
        
        # Ensure metadata has type and timestamp
        self.metadata['type'] = 'relation'
        if 'timestamp' not in self.metadata:
            self.metadata['timestamp'] = datetime.now().isoformat()
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_content(self) -> str:
        """Convert relation to content string for embedding."""
        return f"{self.source_entity} {self.relation_type} {self.target_entity}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert relation memory to dictionary."""
        return {
            'relation_id': self.relation_id,
            'source_entity': self.source_entity,
            'relation_type': self.relation_type,
            'target_entity': self.target_entity,
            'confidence': self.confidence,
            'embedding': self.embedding,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RelationMemory':
        """Create relation memory from dictionary."""
        return cls(
            source_entity=data['source_entity'],
            relation_type=data['relation_type'],
            target_entity=data['target_entity'],
            relation_id=data.get('relation_id', f"rel_{uuid.uuid4().hex[:12]}"),
            confidence=data.get('confidence', 0.9),
            embedding=data.get('embedding'),
            metadata=data.get('metadata', {})
        )

@dataclass
class TemporaryMemory:
    """Short-lived memory that is automatically forgotten after expiry."""
    content: str
    expiry_time: str  # ISO-format expiry timestamp
    temp_id: str = field(default_factory=lambda: f"temp_{uuid.uuid4().hex[:12]}")
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate temporary memory after initialization."""
        if not self.content:
            raise ValueError("Memory content cannot be empty")
        
        try:
            # Validate expiry time format
            datetime.fromisoformat(self.expiry_time)
        except ValueError:
            raise ValueError("Expiry time must be in ISO format")
        
        # Ensure metadata has type and timestamp
        self.metadata['type'] = 'temporary'
        if 'timestamp' not in self.metadata:
            self.metadata['timestamp'] = datetime.now().isoformat()
        self.metadata['expiry_time'] = self.expiry_time
        
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def is_expired(self) -> bool:
        """Check if the memory has expired."""
        expiry = datetime.fromisoformat(self.expiry_time)
        current_time = datetime.now()
        return current_time > expiry
    
    def time_until_expiry(self) -> float:
        """Calculate seconds until expiry (negative if already expired)."""
        expiry = datetime.fromisoformat(self.expiry_time)
        current_time = datetime.now()
        return (expiry - current_time).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert temporary memory to dictionary."""
        return {
            'temp_id': self.temp_id,
            'content': self.content,
            'expiry_time': self.expiry_time,
            'is_expired': self.is_expired(),
            'embedding': self.embedding,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TemporaryMemory':
        """Create temporary memory from dictionary."""
        return cls(
            content=data['content'],
            expiry_time=data['expiry_time'],
            temp_id=data.get('temp_id', f"temp_{uuid.uuid4().hex[:12]}"),
            embedding=data.get('embedding'),
            metadata=data.get('metadata', {})
        )
        
@dataclass
class EpisodeMemory:
    """Memory representing a specific episode or event sequence."""
    title: str
    events: List[Dict[str, Any]]
    episode_id: str = field(default_factory=lambda: f"ep_{uuid.uuid4().hex[:12]}")
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate episode memory after initialization."""
        if not self.title:
            raise ValueError("Episode title cannot be empty")
        if not self.events:
            raise ValueError("Events list cannot be empty")
        
        # Ensure metadata has type and timestamp
        self.metadata['type'] = 'episode'
        if 'timestamp' not in self.metadata:
            self.metadata['timestamp'] = datetime.now().isoformat()
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
        
        # Sanitize events data
        sanitized_events = []
        for event in self.events:
            sanitized_events.append(sanitize_metadata(event))
        self.events = sanitized_events
    
    def add_event(self, event: Dict[str, Any]) -> None:
        """Add an event to the episode."""
        if 'timestamp' not in event:
            event['timestamp'] = datetime.now().isoformat()
        
        # Sanitize the event data
        sanitized_event = sanitize_metadata(event)
        self.events.append(sanitized_event)
        
        # Update metadata with event count
        self.metadata['event_count'] = len(self.events)
        # Ensure metadata is sanitized after updates
        self.metadata = sanitize_metadata(self.metadata)
    
    def end_episode(self) -> None:
        """Mark the episode as complete."""
        self.end_time = datetime.now().isoformat()
        self.metadata['duration_seconds'] = (
            datetime.fromisoformat(self.end_time) -
            datetime.fromisoformat(self.start_time)
        ).total_seconds()
        
        # Ensure metadata is sanitized after updates
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_content(self) -> str:
        """Convert episode to content string for embedding."""
        content_parts = [f"Episode: {self.title}"]
        for idx, event in enumerate(self.events, 1):
            event_desc = event.get('description', f"Event {idx}")
            content_parts.append(f"Event {idx}: {event_desc}")
        return "\n".join(content_parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert episode memory to dictionary."""
        return {
            'episode_id': self.episode_id,
            'title': self.title,
            'events': self.events,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'embedding': self.embedding,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EpisodeMemory':
        """Create episode memory from dictionary."""
        return cls(
            title=data['title'],
            events=data['events'],
            episode_id=data.get('episode_id', f"ep_{uuid.uuid4().hex[:12]}"),
            start_time=data.get('start_time', datetime.now().isoformat()),
            end_time=data.get('end_time'),
            embedding=data.get('embedding'),
            metadata=data.get('metadata', {})
        )
        
@dataclass
class MemoryBatchOperation:
    """Batch operation for efficient memory management."""
    operation_type: str  # 'store', 'retrieve', 'delete', 'search'
    items: List[Any]
    batch_id: str = field(default_factory=lambda: f"batch_{uuid.uuid4().hex[:8]}")
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    timeout: float = 30.0  # seconds
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate batch operation after initialization."""
        valid_operations = {'store', 'retrieve', 'delete', 'search'}
        if self.operation_type not in valid_operations:
            raise ValueError(f"Invalid operation type. Must be one of: {', '.join(valid_operations)}")
        if not self.items:
            raise ValueError("Items list cannot be empty")
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert batch operation to dictionary."""
        return {
            'operation_type': self.operation_type,
            'items': self.items,
            'batch_id': self.batch_id,
            'timestamp': self.timestamp,
            'timeout': self.timeout,
            'metadata': self.metadata
        }

@dataclass
class MemoryGroup:
    """Group of related memories."""
    name: str
    description: str
    memories: List[str] = field(default_factory=list)  # List of memory IDs
    group_id: str = field(default_factory=lambda: f"group_{uuid.uuid4().hex[:12]}")
    tags: Set[str] = field(default_factory=set)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate memory group after initialization."""
        if not self.name:
            raise ValueError("Group name cannot be empty")
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def add_memory(self, memory_id: str) -> None:
        """Add a memory to the group."""
        if memory_id not in self.memories:
            self.memories.append(memory_id)
    
    def remove_memory(self, memory_id: str) -> None:
        """Remove a memory from the group."""
        if memory_id in self.memories:
            self.memories.remove(memory_id)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert memory group to dictionary."""
        return {
            'group_id': self.group_id,
            'name': self.name,
            'description': self.description,
            'memories': self.memories,
            'tags': list(self.tags),
            'created_at': self.created_at,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryGroup':
        """Create memory group from dictionary."""
        group = cls(
            name=data['name'],
            description=data.get('description', ''),
            group_id=data.get('group_id', f"group_{uuid.uuid4().hex[:12]}"),
            created_at=data.get('created_at', datetime.now().isoformat()),
            metadata=data.get('metadata', {})
        )
        
        if 'memories' in data:
            group.memories = data['memories']
            
        if 'tags' in data:
            group.tags = set(data['tags'])
            
        return group
        
@dataclass
class MemoryQuery:
    """Query for searching memories with advanced filters."""
    text: str = ""
    embedding: Optional[List[float]] = None
    metadata_filters: List[Dict[str, Any]] = field(default_factory=list)
    date_range: Optional[tuple[str, str]] = None  # (start_date, end_date) in ISO format
    types: Optional[List[str]] = None
    limit: int = 10
    offset: int = 0
    min_relevance: float = 0.0
    query_id: str = field(default_factory=lambda: f"query_{uuid.uuid4().hex[:8]}")
    
    def __post_init__(self):
        """Validate memory query after initialization."""
        if not self.text and self.embedding is None:
            raise ValueError("Either text or embedding must be provided")
        if self.limit <= 0:
            raise ValueError("Limit must be positive")
        if self.offset < 0:
            raise ValueError("Offset must be non-negative")
        if not (0 <= self.min_relevance <= 1):
            raise ValueError("Minimum relevance must be between 0 and 1")
            
        # Sanitize metadata filters
        sanitized_filters = []
        for filter_dict in self.metadata_filters:
            sanitized_filters.append(sanitize_metadata(filter_dict))
        self.metadata_filters = sanitized_filters
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert memory query to dictionary."""
        return {
            'text': self.text,
            'embedding': self.embedding,
            'metadata_filters': self.metadata_filters,
            'date_range': self.date_range,
            'types': self.types
            }
@dataclass
class MemoryQuery:
    """Query for searching memories with advanced filters."""
    text: str = ""
    embedding: Optional[List[float]] = None
    metadata_filters: List[Dict[str, Any]] = field(default_factory=list)
    date_range: Optional[tuple[str, str]] = None  # (start_date, end_date) in ISO format
    types: Optional[List[str]] = None
    limit: int = 10
    offset: int = 0
    min_relevance: float = 0.0
    query_id: str = field(default_factory=lambda: f"query_{uuid.uuid4().hex[:8]}")
    
    def __post_init__(self):
        """Validate memory query after initialization."""
        if not self.text and self.embedding is None:
            raise ValueError("Either text or embedding must be provided")
        if self.limit <= 0:
            raise ValueError("Limit must be positive")
        if self.offset < 0:
            raise ValueError("Offset must be non-negative")
        if not (0 <= self.min_relevance <= 1):
            raise ValueError("Minimum relevance must be between 0 and 1")
            
        # Sanitize metadata filters
        sanitized_filters = []
        for filter_dict in self.metadata_filters:
            sanitized_filters.append(sanitize_metadata(filter_dict))
        self.metadata_filters = sanitized_filters
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert memory query to dictionary."""
        return {
            'text': self.text,
            'embedding': self.embedding,
            'metadata_filters': self.metadata_filters,
            'date_range': self.date_range,
            'types': self.types,
            'limit': self.limit,
            'offset': self.offset,
            'min_relevance': self.min_relevance,
            'query_id': self.query_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryQuery':
        """Create memory query from dictionary."""
        return cls(
            text=data.get('text', ''),
            embedding=data.get('embedding'),
            metadata_filters=data.get('metadata_filters', []),
            date_range=data.get('date_range'),
            types=data.get('types'),
            limit=data.get('limit', 10),
            offset=data.get('offset', 0),
            min_relevance=data.get('min_relevance', 0.0),
            query_id=data.get('query_id', f"query_{uuid.uuid4().hex[:8]}")
        )
        
@dataclass
class MetaMemory:
    """Memory about memories - for tracking and organization."""
    content: str
    referenced_memories: List[str]  # List of memory IDs
    meta_id: str = field(default_factory=lambda: f"meta_{uuid.uuid4().hex[:12]}")
    operation: str = "organize"  # organize, track, summarize, etc.
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate meta memory after initialization."""
        if not self.content:
            raise ValueError("Content cannot be empty")
        if not self.referenced_memories:
            raise ValueError("Referenced memories cannot be empty")
        
        # Ensure metadata has type and timestamp
        self.metadata['type'] = 'meta_memory'
        self.metadata['operation'] = self.operation
        if 'timestamp' not in self.metadata:
            self.metadata['timestamp'] = datetime.now().isoformat()
            
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert meta memory to dictionary."""
        return {
            'meta_id': self.meta_id,
            'content': self.content,
            'referenced_memories': self.referenced_memories,
            'operation': self.operation,
            'embedding': self.embedding,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MetaMemory':
        """Create meta memory from dictionary."""
        return cls(
            content=data['content'],
            referenced_memories=data['referenced_memories'],
            meta_id=data.get('meta_id', f"meta_{uuid.uuid4().hex[:12]}"),
            operation=data.get('operation', 'organize'),
            embedding=data.get('embedding'),
            metadata=data.get('metadata', {})
        )

@dataclass
class MemoryExportFormat:
    """Configuration for memory export formats."""
    format_type: str  # json, markdown, text, etc.
    include_embeddings: bool = False
    include_metadata: bool = True
    pretty_print: bool = True
    file_extension: str = ""
    nested_structure: bool = True
    time_format: str = "%Y-%m-%d %H:%M:%S"
    
    def __post_init__(self):
        """Validate and set up export format."""
        valid_formats = {'json', 'markdown', 'text', 'csv', 'yaml', 'html', 'xml'}
        if self.format_type not in valid_formats:
            raise ValueError(f"Invalid format type. Must be one of: {', '.join(valid_formats)}")
        
        # Set default file extension if not provided
        if not self.file_extension:
            extensions = {
                'json': 'json',
                'markdown': 'md',
                'text': 'txt',
                'csv': 'csv',
                'yaml': 'yaml',
                'html': 'html',
                'xml': 'xml'
            }
            self.file_extension = extensions.get(self.format_type, 'txt')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert export format to dictionary."""
        return {
            'format_type': self.format_type,
            'include_embeddings': self.include_embeddings,
            'include_metadata': self.include_metadata,
            'pretty_print': self.pretty_print,
            'file_extension': self.file_extension,
            'nested_structure': self.nested_structure,
            'time_format': self.time_format
        }

@dataclass
class MemoryExport:
    """Container for exported memories."""
    memories: List[Dict[str, Any]]
    format: MemoryExportFormat
    export_id: str = field(default_factory=lambda: f"export_{uuid.uuid4().hex[:8]}")
    export_time: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Set up export metadata."""
        self.metadata['memory_count'] = len(self.memories)
        self.metadata['export_time'] = self.export_time
        self.metadata['format'] = self.format.format_type
        
        # Sanitize metadata for compatibility with storage backends
        self.metadata = sanitize_metadata(self.metadata)
        
        # Sanitize memories metadata
        for memory in self.memories:
            if 'metadata' in memory:
                memory['metadata'] = sanitize_metadata(memory['metadata'])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert export to dictionary."""
        return {
            'memories': self.memories,
            'format': self.format.to_dict(),
            'export_id': self.export_id,
            'export_time': self.export_time,
            'metadata': self.metadata
        }
        
@dataclass
class MemoryImportConfig:
    """Configuration for memory import operations."""
    source_format: str  # json, markdown, text, etc.
    override_existing: bool = False
    generate_embeddings: bool = True
    mapping: Dict[str, str] = field(default_factory=dict)  # Source field to target field mapping
    default_metadata: Dict[str, Any] = field(default_factory=dict)
    validate_schema: bool = True
    
    def __post_init__(self):
        """Validate import configuration."""
        valid_formats = {'json', 'markdown', 'text', 'csv', 'yaml', 'html', 'xml'}
        if self.source_format not in valid_formats:
            raise ValueError(f"Invalid source format. Must be one of: {', '.join(valid_formats)}")
            
        # Sanitize default metadata
        self.default_metadata = sanitize_metadata(self.default_metadata)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert import configuration to dictionary."""
        return {
            'source_format': self.source_format,
            'override_existing': self.override_existing,
            'generate_embeddings': self.generate_embeddings,
            'mapping': self.mapping,
            'default_metadata': self.default_metadata,
            'validate_schema': self.validate_schema
        }
        
@dataclass
class MemoryImportStats:
    """Statistics for memory import operations."""
    total_memories: int = 0
    successful_imports: int = 0
    failed_imports: int = 0
    skipped_memories: int = 0
    embeddings_generated: int = 0
    import_time: float = 0.0  # seconds
    errors: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def record_success(self) -> None:
        """Record a successful import."""
        self.successful_imports += 1
        self.total_memories += 1
    
    def record_failure(self, memory_id: str, error: str) -> None:
        """Record a failed import."""
        self.failed_imports += 1
        self.total_memories += 1
        self.errors.append({
            'memory_id': memory_id,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })
    
    def record_skip(self) -> None:
        """Record a skipped memory."""
        self.skipped_memories += 1
        self.total_memories += 1
    
    def record_embedding(self) -> None:
        """Record a generated embedding."""
        self.embeddings_generated += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            'total_memories': self.total_memories,
            'successful_imports': self.successful_imports,
            'failed_imports': self.failed_imports,
            'skipped_memories': self.skipped_memories,
            'embeddings_generated': self.embeddings_generated,
            'import_time': self.import_time,
            'errors': self.errors,
            'timestamp': self.timestamp,
            'success_rate': self.successful_imports / max(1, self.total_memories)
        }
        
@dataclass
class MemorySyncConfig:
    """Configuration for memory synchronization between stores."""
    source_store: str
    target_store: str
    sync_type: str = "incremental"  # full, incremental
    conflict_resolution: str = "newer"  # newer, source_wins, target_wins, merge
    batch_size: int = 100
    sync_interval: int = 3600  # seconds
    include_types: Optional[List[str]] = None
    exclude_types: Optional[List[str]] = None
    verify_sync: bool = True
    
    def __post_init__(self):
        """Validate sync configuration."""
        valid_sync_types = {'full', 'incremental'}
        if self.sync_type not in valid_sync_types:
            raise ValueError(f"Invalid sync type. Must be one of: {', '.join(valid_sync_types)}")
        
        valid_conflict_resolutions = {'newer', 'source_wins', 'target_wins', 'merge'}
        if self.conflict_resolution not in valid_conflict_resolutions:
            raise ValueError(f"Invalid conflict resolution. Must be one of: {', '.join(valid_conflict_resolutions)}")
        
        if self.batch_size <= 0:
            raise ValueError("Batch size must be positive")
        if self.sync_interval <= 0:
            raise ValueError("Sync interval must be positive")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert sync configuration to dictionary."""
        return {
            'source_store': self.source_store,
            'target_store': self.target_store,
            'sync_type': self.sync_type,
            'conflict_resolution': self.conflict_resolution,
            'batch_size': self.batch_size,
            'sync_interval': self.sync_interval,
            'include_types': self.include_types,
            'exclude_types': self.exclude_types,
            'verify_sync': self.verify_sync
        }

@dataclass
class MemorySyncStats:
    """Statistics for memory synchronization operations."""
    source_store: str
    target_store: str
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    total_memories: int = 0
    synced_memories: int = 0
    conflicts: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    next_sync_time: Optional[str] = None
    
    def complete_sync(self) -> None:
        """Mark synchronization as complete."""
        self.end_time = datetime.now().isoformat()
        self.duration_seconds = (
            datetime.fromisoformat(self.end_time) - 
            datetime.fromisoformat(self.start_time)
        ).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert sync stats to dictionary."""
        return {
            'source_store': self.source_store,
            'target_store': self.target_store,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'total_memories': self.total_memories,
            'synced_memories': self.synced_memories,
            'conflicts': self.conflicts,
            'errors': self.errors,
            'duration_seconds': self.duration_seconds,
            'next_sync_time': self.next_sync_time,
            'success_rate': self.synced_memories / max(1, self.total_memories)
        }            
