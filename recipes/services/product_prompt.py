"""
Convenience wrapper around build_recipe_prompt() (see prompts.py) that
accepts a list/queryset of Product model instances directly, as
required by this ticket's acceptance criteria ("Accepts list of Product
objects").

Reuses the team's agreed-upon "rich" response schema (ingredients_used,
missing_ingredients, instructions, prep_time_minutes) rather than a
separate simplified one - per team decision: a richer schema now gives
more flexibility later (e.g. showing missing ingredients as a shopping
list, or prep_time_minutes as a filter), and unused fields can simply
be ignored/not displayed by the frontend rather than requiring a
schema migration down the line.
"""

from recipes.services.prompts import build_recipe_prompt


def build_prompt_from_products(products, today=None):
    """
    Builds the full Gemini prompt directly from a list/queryset of
    Product model instances (e.g. Product.objects.filter(user=...)).

    Internally converts each Product into the {name, expiry_date} shape
    that build_recipe_prompt() already expects, so all of its existing,
    tested behavior is reused as-is:
      - prioritizes products with the nearest expiry_date first
      - handles the empty fridge edge case gracefully
      - handles the single ingredient edge case
      - requests the team's standard "rich" JSON schema

    Args:
        products: an iterable of Product model instances. Each product
            is expected to have `.name` and `.expiry_date` attributes.
        today: optional date to use as "now" reference (mainly for
            tests). Defaults to date.today().

    Returns:
        A formatted prompt string ready to send to the Gemini API.
    """
    ingredient_dicts = [
        {"name": product.name, "expiry_date": product.expiry_date}
        for product in products
    ]
    return build_recipe_prompt(ingredient_dicts, today=today)