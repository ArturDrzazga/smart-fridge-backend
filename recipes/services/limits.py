from datetime import datetime, timedelta, timezone

from django.core.cache import cache

DAILY_LIMIT = 5

def get_redis_limit_key(user_id):
    current_data = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"ai_limit:{user_id}:{current_data}"

def check_daily_limit(user_id):
    """
    Checks the status of the user's limit.
    Returns a tuple: (is_allowed, remaining_requests)
    """
    key = get_redis_limit_key(user_id)

    current_count = cache.get(key)
    if current_count is None:
        current_count = 0
    else:
        current_count = int(current_count)

    if current_count >= DAILY_LIMIT:
        return False, 0

    new_count = current_count + 1

    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0,
                                                 minute=0,
                                                 second=0,
                                                 microsecond=0
                                                 )
    seconds_to_midnight = int((tomorrow - now).total_seconds())

    cache.set(key, new_count, timeout=seconds_to_midnight)
    remaining = DAILY_LIMIT - new_count
    return True, remaining

def get_remaining_requests(user_id):
    key = get_redis_limit_key(user_id)
    current_count = cache.get(key)
    if current_count is None:
        return DAILY_LIMIT
    return max(0, DAILY_LIMIT - int(current_count))