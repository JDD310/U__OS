import json

import redis.asyncio as aioredis

from config import settings

_redis = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def subscribe_processed_events():
    """Return a pub/sub object subscribed to the processed_events channel."""
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("processed_events")
    return pubsub
