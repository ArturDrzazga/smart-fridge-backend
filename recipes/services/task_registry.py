"""
Tracks which user submitted which Celery task_id, so
GET /api/recipes/suggestions/<task_id>/ can:

  - return 404 for task_ids that were never actually submitted.
    Celery's AsyncResult(task_id) can't distinguish "this task_id was
    never created" from "it exists but hasn't started yet" - both
    report status PENDING. Without our own registry, any random string
    (or guessed UUID) looks like a valid, in-progress task forever.

  - return 404 (never leak the task's data) if the task belongs to a
    different user, instead of allowing anyone who observes/guesses a
    task_id to read someone else's recipe suggestions.
"""

import os

import redis

# Match Celery's typical result-backend expiration window, so a task_id
# doesn't vanish from our registry meaningfully before its actual
# result would expire anyway.
TASK_REGISTRY_TTL_SECONDS = 24 * 60 * 60

_redis_client = None


def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        _redis_client = redis.Redis.from_url(redis_url)
    return _redis_client


def register_task(task_id, user_id):
    """Records that `user_id` submitted `task_id`, so its existence and
    ownership can be verified later when the status is queried."""
    key = f"recipe_task_owner:{task_id}"
    _get_redis_client().set(key, str(user_id), ex=TASK_REGISTRY_TTL_SECONDS)


def get_task_owner(task_id):
    """
    Returns the user_id (as a string) that submitted this task_id, or
    None if this task_id was never registered (or its registry entry
    has expired).
    """
    key = f"recipe_task_owner:{task_id}"
    value = _get_redis_client().get(key)
    return value.decode() if value is not None else None