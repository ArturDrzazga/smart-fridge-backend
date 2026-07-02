import json
import os

from google import genai


def _get_client():
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def _get_model():
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def test_gemini_connection():
    client = _get_client()
    model = _get_model()

    response = client.models.generate_content(
        model=model,
        contents="Give me 3 simple recipe ideas using eggs, tomatoes, and cheese.",
    )

    return response.text


def generate_recipe_suggestions(ingredients):
    client = _get_client()
    model = _get_model()

    ingredients_text = ", ".join(ingredients)

    prompt = f"""
You are a cooking assistant.

Based only on these ingredients: {ingredients_text}

Return exactly 3 recipe suggestions in valid JSON.
Use this schema:
{{
  "recipes": [
    {{
      "title": "string",
      "ingredients_used": ["string"],
      "missing_ingredients": ["string"],
      "instructions": ["string"],
      "prep_time_minutes": 0
    }}
  ]
}}

Rules:
- Return only JSON
- No markdown
- No explanation outside JSON
- Keep recipes simple and realistic
- Prefer recipes that mostly use the provided ingredients
"""

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
        },
    )

    return json.loads(response.text)