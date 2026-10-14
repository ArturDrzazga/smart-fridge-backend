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

  - report a TIMEOUT when a task has been PENDING for too long (for
    example the worker is asleep or never picked it up), instead of
    letting clients poll a 200 PENDING response forever.
"""

import os
import time

import redis

# Match Celery's typical result-backend expiration window, so a task_id
# doesn't vanish from our registry meaningfully before its actual
# result would expire anyway.
TASK_REGISTRY_TTL_SECONDS = 24 * 60 * 60

# A task that is still PENDING after this many seconds is reported to
# the client as TIMEOUT. Generous enough for a cold-started free-tier
# worker plus a slow Gemini call.
TASK_PENDING_TIMEOUT_SECONDS = 120

_redis_client = None


def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        _redis_client = redis.Redis.from_url(redis_url)
    return _redis_client


def register_task(task_id, user_id):
    """Records that `user_id` submitted `task_id` (and when), so its
    existence, ownership and age can be verified later when the status
    is queried."""
    client = _get_redis_client()
    client.set(
        f"recipe_task_owner:{task_id}",
        str(user_id),
        ex=TASK_REGISTRY_TTL_SECONDS,
    )
    client.set(
        f"recipe_task_created:{task_id}",
        str(int(time.time())),
        ex=TASK_REGISTRY_TTL_SECONDS,
    )


def get_task_owner(task_id):
    """
    Returns the user_id (as a string) that submitted this task_id, or
    None if this task_id was never registered (or its registry entry
    has expired).
    """
    key = f"recipe_task_owner:{task_id}"
    value = _get_redis_client().get(key)
    return value.decode() if value is not None else None


def get_task_age_seconds(task_id):
    """
    Returns how many seconds ago this task was submitted, or None if the
    submission time is unknown (task registered before this feature
    existed, or its registry entry expired).
    """
    value = _get_redis_client().get(f"recipe_task_created:{task_id}")
    if value is None:
        return None
    return max(0, int(time.time()) - int(value.decode()))


def is_task_timed_out(task_id):
    """True if the task was submitted more than
    TASK_PENDING_TIMEOUT_SECONDS ago."""
    age = get_task_age_seconds(task_id)
    return age is not None and age > TASK_PENDING_TIMEOUT_SECONDS