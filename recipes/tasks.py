from celery import shared_task

from fridge.models import Product
from recipes.services.gemini_service import generate_recipe_suggestions


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