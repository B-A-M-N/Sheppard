"""
Specialized storage interface for user preferences.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from src.memory.stores.base import BaseMemoryStore
from src.memory.models import Memory, MemorySearchResult
from src.memory.exceptions import (
    MemoryValidationError,
    StorageError,
    RetrievalError
)
from .schemas import PreferenceSchema, PreferenceSetSchema, PreferenceSearchSchema

logger = logging.getLogger(__name__)

class PreferenceStore:
    """Manages storage and retrieval of user preferences."""
    
    def __init__(self, memory_store: BaseMemoryStore):
        """
        Initialize preference store.
        
        Args:
            memory_store: Base memory store instance
        """
        self.store = memory_store
        self.preference_types = {
            "color",
            "flavor",
            "destination",
            "food",
            "music",
            "hobby",
            "animal"
        }
    
    def _validate_preference(
        self,
        pref_type: str,
        value: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a preference value.
        
        Args:
            pref_type: Type of preference
            value: Preference value
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        if not pref_type or not value:
            return False, "Preference type and value must not be empty"
        
        if pref_type.lower() not in self.preference_types:
            return False, f"Unknown preference type: {pref_type}"
        
        if len(value) > 100:  # Reasonable limit for preference values
            return False, "Preference value too long"
            
        return True, None
    
    def _format_preference_content(
        self,
        pref_type: str,
        value: str
    ) -> str:
        """Format preference for storage."""
        return f"User's favorite {pref_type} is {value}"
    
    def _extract_preferences(
        self,
        content: str
    ) -> Dict[str, str]:
        """
        Extract preferences from content.
        
        Args:
            content: Text content to extract from
            
        Returns:
            Dict[str, str]: Extracted preferences
        """
        preferences = {}
        content_lower = content.lower()
        
        # Look for preference patterns
        for pref_type in self.preference_types:
            if f"favorite {pref_type}" in content_lower:
                # Find the value after "is"
                parts = content_lower.split(f"favorite {pref_type} is ")
                if len(parts) > 1:
                    value = parts[1].split(".")[0].strip()
                    if value:
                        preferences[pref_type] = value
        
        return preferences
    
    async def store_preference(
        self,
        pref_type: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store a single preference.
        
        Args:
            pref_type: Type of preference
            value: Preference value
            metadata: Optional additional metadata
            
        Returns:
            str: Memory ID
            
        Raises:
            MemoryValidationError: If preference is invalid
            StorageError: If storage fails
        """
        try:
            # Validate preference
            is_valid, error = self._validate_preference(pref_type, value)
            if not is_valid:
                raise MemoryValidationError(error)
            
            # Create preference schema
            preference = PreferenceSchema(
                type=pref_type,
                value=value,
                timestamp=datetime.now().isoformat(),
                metadata=metadata or {}
            )
            
            # Prepare content and metadata
            content = self._format_preference_content(pref_type, value)
            full_metadata = {
                "type": "preference",
                "preference_type": pref_type,
                "preference_value": value,
                "timestamp": preference.timestamp,
                **(metadata or {})
            }
            
            # Store in memory system
            return await self.store.store(Memory(
                content=content,
                metadata=full_metadata
            ))
            
        except Exception as e:
            logger.error(f"Failed to store preference: {str(e)}")
            raise StorageError(f"Failed to store preference: {str(e)}")
    
    async def store_preference_set(
        self,
        preferences: Dict[str, str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Store multiple preferences together.
        
        Args:
            preferences: Dict of preference types to values
            metadata: Optional additional metadata
            
        Returns:
            List[str]: List of memory IDs
            
        Raises:
            MemoryValidationError: If any preference is invalid
            StorageError: If storage fails
        """
        try:
            memory_ids = []
            timestamp = datetime.now().isoformat()
            
            # Create preference set schema
            pref_schemas = {}
            for pref_type, value in preferences.items():
                # Validate each preference
                is_valid, error = self._validate_preference(pref_type, value)
                if not is_valid:
                    raise MemoryValidationError(
                        f"Invalid {pref_type} preference: {error}"
                    )
                
                # Create schema
                pref_schemas[pref_type] = PreferenceSchema(
                    type=pref_type,
                    value=value,
                    timestamp=timestamp
                )
            
            preference_set = PreferenceSetSchema(
                preferences=pref_schemas,
                timestamp=timestamp,
                metadata=metadata or {}
            )
            
            # Store each preference
            for pref_type, schema in preference_set.preferences.items():
                memory_id = await self.store_preference(
                    pref_type,
                    schema.value,
                    metadata={
                        "preference_set_time": timestamp,
                        **(metadata or {})
                    }
                )
                memory_ids.append(memory_id)
            
            return memory_ids
            
        except Exception as e:
            logger.error(f"Failed to store preference set: {str(e)}")
            raise StorageError(f"Failed to store preference set: {str(e)}")
    
    async def get_preference(
        self,
        pref_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the latest value for a specific preference type.
        
        Args:
            pref_type: Type of preference to retrieve
            
        Returns:
            Optional[Dict[str, Any]]: Preference data if found
            
        Raises:
            RetrievalError: If retrieval fails
        """
        try:
            # Search for preferences of this type using simplified filter
            results = await self.store.search(
                f"favorite {pref_type}",
                metadata_filter={"type": "preference"},  # Simplified filter
                limit=1  # Only get the most recent
            )
            
            if not results:
                return None
            
            # Get the most recent result
            memory = results[0]
            
            return {
                "type": pref_type,
                "value": memory.metadata.get("preference_value"),
                "timestamp": memory.metadata.get("timestamp"),
                "metadata": memory.metadata
            }
            
        except Exception as e:
            logger.error(f"Failed to retrieve preference: {str(e)}")
            raise RetrievalError(f"Failed to retrieve preference: {str(e)}")
    
    async def get_all_preferences(
        self
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get all stored preferences.
        
        Returns:
            Dict[str, Dict[str, Any]]: Map of preference types to values
            
        Raises:
            RetrievalError: If retrieval fails
        """
        try:
            preferences = {}
            
            # Get preferences for each type
            for pref_type in self.preference_types:
                pref = await self.get_preference(pref_type)
                if pref:
                    preferences[pref_type] = pref
            
            return preferences
            
        except Exception as e:
            logger.error(f"Failed to retrieve preferences: {str(e)}")
            raise RetrievalError(f"Failed to retrieve preferences: {str(e)}")
    
    async def search_preferences(
        self,
        query: str,
        limit: int = 5
    ) -> List[MemorySearchResult]:
        """
        Search for preference-related memories.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List[MemorySearchResult]: Search results
            
        Raises:
            RetrievalError: If search fails
        """
        try:
            return await self.store.search(
                query,
                metadata_filter={"type": "preference"},  # Simple type filter
                limit=limit
            )
            
        except Exception as e:
            logger.error(f"Failed to search preferences: {str(e)}")
            raise RetrievalError(f"Failed to search preferences: {str(e)}")
    
    async def extract_and_store_preferences(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Extract and store preferences from text content.
        
        Args:
            content: Text content to extract from
            metadata: Optional additional metadata
            
        Returns:
            List[str]: List of stored memory IDs
            
        Raises:
            StorageError: If storage fails
        """
        try:
            # Extract preferences
            preferences = self._extract_preferences(content)
            
            if not preferences:
                return []
            
            # Store as a set
            return await self.store_preference_set(
                preferences,
                metadata={
                    "source_content": content,
                    **(metadata or {})
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to extract and store preferences: {str(e)}")
            raise StorageError(
                f"Failed to extract and store preferences: {str(e)}"
            )
