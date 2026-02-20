import json

import redis.asyncio as aioredis

from config import settings

_redis = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url)
    return _redis


async def publish_raw_message(payload: dict) -> None:
    r = await get_redis()
    await r.publish("raw_messages", json.dumps(payload, default=str))
