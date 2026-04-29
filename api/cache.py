import json
import logging
from typing import Any

import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
        )
    return _redis_client


# ---------- key schema ----------
# All cache keys go through these functions.
# Never construct a key string anywhere else in the codebase.

def link_key(shortcode: str) -> str:
    return f"link:v1:{shortcode}"


def stats_key(shortcode: str) -> str:
    return f"stats:v1:{shortcode}"


# ---------- operations ----------

async def get_cached_link(shortcode: str) -> dict | None:
    try:
        redis = get_redis()
        raw = await redis.get(link_key(shortcode))
        if raw:
            return json.loads(raw)
        return None
    except Exception as e:
        logger.warning("Cache read failed for %s: %s", shortcode, e)
        return None


async def set_cached_link(shortcode: str, data: dict, ttl: int | None = None) -> None:
    try:
        redis = get_redis()
        await redis.setex(
            link_key(shortcode),
            ttl or settings.cache_ttl_seconds,
            json.dumps(data, default=str),
        )
    except Exception as e:
        logger.warning("Cache write failed for %s: %s", shortcode, e)


async def invalidate_link(shortcode: str) -> None:
    try:
        redis = get_redis()
        await redis.delete(link_key(shortcode), stats_key(shortcode))
    except Exception as e:
        logger.warning("Cache invalidation failed for %s: %s", shortcode, e)


async def increment_click_count(shortcode: str) -> None:
    """
    Atomically increment click count in cache.
    Only updates if key exists — avoids caching stale data on a cold cache.
    """
    try:
        redis = get_redis()
        key = stats_key(shortcode)
        exists = await redis.exists(key)
        if exists:
            await redis.hincrby(key, "click_count", 1)
    except Exception as e:
        logger.warning("Cache click increment failed for %s: %s", shortcode, e)


async def ping() -> bool:
    try:
        redis = get_redis()
        return await redis.ping()
    except Exception:
        return False