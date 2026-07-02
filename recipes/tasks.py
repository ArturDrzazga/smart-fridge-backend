from celery import shared_task

from recipes.services.gemini_service import generate_recipe_suggestions


@shared_task
def generate_recipe_suggestions_task(ingredients):
    return generate_recipe_suggestions(ingredients)qq