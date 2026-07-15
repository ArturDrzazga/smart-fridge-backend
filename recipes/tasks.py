import logging

from celery import shared_task
from django.core.cache import cache

from recipes.services.gemini_service import generate_recipe_suggestions

logger = logging.getLogger("django")

@shared_task(
    bind=True,
    max_retries=1,
    default_retry_delay=5,
    autoretry_for=(Exception,),
)
def generate_recipe_task(self, user_id, ingredients):
    logger.info(f"Starting recipe generation task for user {user_id}")
    try:
        recipe_data = generate_recipe_suggestions(ingredients)
        cache_key = f"user_recipe_{user_id}"
        cache.set(cache_key, recipe_data, timeout=3600)

        logger.info(f"Successfully generated and cached recipe for user {user_id}")
        return recipe_data

    except Exception as exc:
        logger.error(f"Error generating recipe for user {user_id}: {str(exc)}")
        raise self.retry(exc=exc)