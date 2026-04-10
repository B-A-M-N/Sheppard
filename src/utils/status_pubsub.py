"""
Structured status publisher for background tasks.
Fire-and-forget pub/sub to sheppard:status channel.
"""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CHANNEL = "sheppard:status"


async def publish_status(redis_client, component: str, event: str, data: dict):
    """
    Publish a structured status event.
    Fire-and-forget — never crashes the caller.

    Args:
        redis_client: redis.asyncio.Redis, RedisStoresImpl, or adapter with publish/client
        component: identifier (e.g., "vampire-3", "frontier", "distillery")
        event: event type (e.g., "stats", "mission_start", "batch_complete")
        data: arbitrary dict of event-specific metrics/context
    """
    try:
        payload = json.dumps({
            "component": component,
            "event": event,
            "data": data,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        # Handle multiple client types:
        # 1. Raw redis.asyncio.Redis — has publish() directly
        # 2. RedisStoresImpl adapter — wraps raw client as .client
        # 3. Adapter with .publish() method
        if hasattr(redis_client, 'publish') and callable(redis_client.publish):
            await redis_client.publish(CHANNEL, payload)
        elif hasattr(redis_client, 'client') and hasattr(redis_client.client, 'publish'):
            await redis_client.client.publish(CHANNEL, payload)
        elif hasattr(redis_client, '_pool') and redis_client._pool:
            await redis_client._pool.publish(CHANNEL, payload)
        else:
            await redis_client.publish(CHANNEL, payload)
    except Exception as e:
        logger.debug(f"[StatusPub] Failed to publish {component}/{event}: {e}")
