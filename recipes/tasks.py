import json
import logging

from celery import shared_task
from django.core.cache import cache

from recipes.exceptions import GeminiTimeoutError
from fridge.models import Product
from recipes.services.gemini_service import generate_recipe_suggestions
from recipes.services.parser import parse_gemini_response

logger = logging.getLogger("django")

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def generate_recipe_task(self, user_id, ingredients):
    logger.info(f"Starting recipe generation task for user {user_id}")
    try:
        raw_data = generate_recipe_suggestions(ingredients)

        if isinstance(raw_data, dict):
            raw_text = json.dumps(raw_data)
        else:
            raw_text = str(raw_data)

        structured_recipes = parse_gemini_response(raw_text)

        cache_key = f"user_recipe_{user_id}"
        cache.set(cache_key, {"recipes": structured_recipes}, timeout=3600)

        logger.info(f"Successfully generated, parsed, "
                    f"and cached recipe for user {user_id}")
        return {"recipes": structured_recipes}

    except Exception as exc:
        logger.error(f"Error generating recipe for user {user_id}: {str(exc)}")

        if self.request.retries >= self.max_retries:
            raise GeminiTimeoutError()

        # Exponential backoff computed explicitly (5s, 10s, 20s, capped
        # at 60s). retry_backoff=True only applies automatically when
        # Celery's autoretry_for triggers the retry - it has no effect
        # on an explicit self.retry() call made from inside a manual
        # try/except, which is what we do here. We also no longer use
        # autoretry_for, since combining it with a manual retry caused
        # Celery to attempt to auto-retry GeminiTimeoutError itself,
        # even though that's meant to be the final, non-retryable error
        # raised once max_retries is exhausted.
        backoff_seconds = min(5 * (2 ** self.request.retries), 60)
        raise self.retry(exc=exc, countdown=backoff_seconds)


def _get_user_fridge_ingredients(user_id):
    """
    Fetch the given user's fridge/freezer contents from the database,
    formatted for build_recipe_prompt() (name + expiry_date), sorted
    soonest-expiring first.
    """
    products = (
        Product.objects.filter(user_id=user_id)
        .order_by("expiry_date")
        .values("name", "expiry_date")
    )
    return [
        {
            "name": product["name"],
            "expiry_date": product["expiry_date"].isoformat(),
        }
        for product in products
    ]


@shared_task
def generate_recipe_suggestions_task(user_id, ingredients=None):
    """
    If `ingredients` is None (or empty), automatically fetch the user's
    current fridge contents from the database instead, so recipes are
    generated from ingredients they actually have, prioritizing items
    closest to their expiry date.
    """
    if not ingredients:
        ingredients = _get_user_fridge_ingredients(user_id)

    return generate_recipe_suggestions(ingredients)