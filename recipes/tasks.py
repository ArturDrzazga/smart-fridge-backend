import json
import logging

from celery import shared_task
from django.core.cache import cache

from recipes.services.gemini_service import generate_recipe_suggestions
from recipes.services.parser import parse_gemini_response

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
        raise self.retry(exc=exc)