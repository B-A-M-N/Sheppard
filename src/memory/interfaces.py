# src/memory/interfaces.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class MemoryInterface(ABC):
    @abstractmethod
    async def store(self, content: str, metadata: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    async def retrieve(self, memory_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        pass
