"""
Simple Redis-backed daily rate limiter, used by POST /api/recipes/generate/
to enforce a per-user daily request limit (SFA-429 / acceptance criteria:
"Returns 429 if daily request limit reached").
"""

import os
from datetime import date

import redis

DAILY_RECIPE_GENERATION_LIMIT = 5

_redis_client = None


def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        _redis_client = redis.Redis.from_url(redis_url)
    return _redis_client


def check_and_increment_daily_limit(user_id, limit=DAILY_RECIPE_GENERATION_LIMIT):
    """
    Checks whether the given user is still within their daily request
    limit. If they are, atomically increments their counter and returns
    True. If the limit has already been reached, returns False without
    incrementing further.

    The counter is keyed per user per calendar day and expires after 24h,
    so it naturally resets at midnight without any separate cleanup job.
    """
    client = _get_redis_client()
    key = f"recipe_generate_limit:{user_id}:{date.today().isoformat()}"

    current = client.get(key)
    current_count = int(current) if current else 0

    if current_count >= limit:
        return False

    pipe = client.pipeline()
    pipe.incr(key, 1)
    pipe.expire(key, 86400)
    pipe.execute()
    return True


def get_remaining_requests(user_id, limit=DAILY_RECIPE_GENERATION_LIMIT):
    """Returns how many requests the user has left today (for debugging/UI)."""
    client = _get_redis_client()
    key = f"recipe_generate_limit:{user_id}:{date.today().isoformat()}"
    current = client.get(key)
    current_count = int(current) if current else 0
    return max(0, limit - current_count)