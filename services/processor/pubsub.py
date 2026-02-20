import json

import redis.asyncio as aioredis

from config import settings

_redis = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url)
    return _redis


async def subscribe_raw_messages():
    """Return a pub/sub object subscribed to the raw_messages channel."""
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("raw_messages")
    return pubsub


async def publish_processed_event(payload: dict) -> None:
    """Publish a processed event to the processed_events channel."""
    r = await get_redis()
    await r.publish("processed_events", json.dumps(payload, default=str))
