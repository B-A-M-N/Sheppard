import json
import logging
from typing import Optional
from .working_state import WorkingState

logger = logging.getLogger(__name__)

class WorkingStateStore:
    """
    Redis-backed persistent storage for session-scoped cognitive state.
    TTL default: 24 hours.
    """
    
    KEY_PREFIX = "cmk:working_state:"
    DEFAULT_TTL = 86400  # 24 hours
    
    def __init__(self, redis_client):
        """
        Args:
            redis_client: redis.asyncio.Redis instance.
        """
        self.redis = redis_client

    async def load(self, session_id: str) -> Optional[WorkingState]:
        """Load session state from Redis."""
        key = f"{self.KEY_PREFIX}{session_id}"
        try:
            data_bytes = await self.redis.get(key)
            if not data_bytes:
                return None
            
            # Redis client might return string or bytes depending on config
            if isinstance(data_bytes, bytes):
                data_str = data_bytes.decode("utf-8")
            else:
                data_str = data_bytes
                
            data = json.loads(data_str)
            return WorkingState.from_dict(data)
        except Exception as e:
            logger.error(f"[WorkingStateStore] Failed to load session {session_id}: {e}")
            return None

    async def save(self, state: WorkingState, ttl: int = DEFAULT_TTL) -> bool:
        """Persist session state to Redis."""
        key = f"{self.KEY_PREFIX}{state.session_id}"
        try:
            data_str = json.dumps(state.to_dict())
            await self.redis.set(key, data_str, ex=ttl)
            return True
        except Exception as e:
            logger.error(f"[WorkingStateStore] Failed to save session {state.session_id}: {e}")
            return False

    async def delete(self, session_id: str) -> bool:
        """Explicitly remove session state from Redis."""
        key = f"{self.KEY_PREFIX}{session_id}"
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"[WorkingStateStore] Failed to delete session {session_id}: {e}")
            return False

    async def touch(self, session_id: str, ttl: int = DEFAULT_TTL) -> bool:
        """Reset TTL for an existing session."""
        key = f"{self.KEY_PREFIX}{session_id}"
        try:
            return await self.redis.expire(key, ttl)
        except Exception as e:
            logger.error(f"[WorkingStateStore] Failed to touch session {session_id}: {e}")
            return False
