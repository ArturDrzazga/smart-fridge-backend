import json
import os

from google import genai

from recipes.services.prompts import build_recipe_prompt


def _get_client():
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def _get_model():
    return os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


def test_gemini_connection():
    client = _get_client()
    model = _get_model()
    response = client.models.generate_content(
        model=model,
        contents="Give me 3 simple recipe ideas using eggs, tomatoes, and cheese.",
    )
    return response.text


def generate_recipe_suggestions(ingredients):
    """
    Generate recipe suggestions from a list of ingredients.

    `ingredients` can be:
      - a list of plain strings, e.g. ["eggs", "tomatoes", "cheese"]
      - a list of dicts with expiry info, e.g.
        [{"name": "eggs", "expiry_date": "2026-07-12"}, {"name": "flour"}]

    When expiry dates are provided, the prompt asks Gemini to prioritize
    recipes that use ingredients closer to expiring, to help reduce food
    waste.
    """
    client = _get_client()
    model = _get_model()

    prompt = build_recipe_prompt(ingredients)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
        },
    )
    return json.loads(response.text)