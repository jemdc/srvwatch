"""
Redis cache for the latest metrics snapshot per server.
Used by the /live endpoint so the frontend gets instant responses
without hitting the database on every poll.
"""

import json
import os
from typing import Optional

import redis.asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL = 60   # seconds — expire stale entries after 1 minute

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def set_latest(server_id: str, payload: dict) -> None:
    r = await get_redis()
    key = f"srvwatch:latest:{server_id}"
    await r.setex(key, CACHE_TTL, json.dumps(payload))


async def get_latest(server_id: str) -> Optional[dict]:
    r = await get_redis()
    key = f"srvwatch:latest:{server_id}"
    raw = await r.get(key)
    return json.loads(raw) if raw else None


async def set_server_status(server_id: str, online: bool) -> None:
    r = await get_redis()
    key = f"srvwatch:status:{server_id}"
    await r.setex(key, CACHE_TTL * 2, "1" if online else "0")


async def get_server_status(server_id: str) -> Optional[bool]:
    r = await get_redis()
    key = f"srvwatch:status:{server_id}"
    val = await r.get(key)
    if val is None:
        return None
    return val == "1"


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
