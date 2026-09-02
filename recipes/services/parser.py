import json
import logging

logger = logging.getLogger("django")

def parse_gemini_response(raw_response_text):
    """
    Parses raw Gemini response text into validated structures.
    Handles malformed JSON and missing fields gracefully.
    """
    if not raw_response_text:
        logger.warning("Received an empty response from Gemini")
        return []

    try:
        cleaned_text = raw_response_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text.split("```json", 1)[1]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text.rsplit("```", 1)[0]
        cleaned_text = cleaned_text.strip()

        data = json.loads(cleaned_text)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Malformed JSON from Gemini: {str(e)}. "
                     f"Raw text: {raw_response_text}")

        return [
            {
                "title": "Error generating recipe",
                "ingredients": [],
                "steps": ["The AI generated an invalid recipe structure. "
                          "Please try again."]
            }
        ]

    recipes_list = data.get("recipes", []) if isinstance(data, dict) else data
    if not isinstance(recipes_list, list):
        recipes_list = data

    parsed_recipes = []

    for index, item in enumerate(recipes_list):
        if not isinstance(item, dict):
            continue

        title = item.get("title")
        steps = item.get("instructions")
        ingredients = item.get("ingredients") or item.get("ingredients_used")
        prep_time_minutes = item.get("prep_time_minutes")
        difficulty = item.get("difficulty")
        description = item.get("description")
        servings = item.get("servings")

        if not title:
            logger.warning(f"Recipe at index {index} is missing a title. Skipping.")

        if not isinstance(ingredients, list):
            ingredients = [ingredients] if ingredients else []

        if not isinstance (steps, list):
            steps = [steps] if steps else ["No instructions provided by AI."]

        recipe_entry = {
            "title": str(title),
            "ingredients": [str(i) for i in ingredients],
            "steps": [str(s) for s in steps],
            "prep_time_minutes": prep_time_minutes,
            "difficulty": difficulty,
            "description": description,
            "servings": servings,
        }
        parsed_recipes.append(recipe_entry)

    return parsed_recipes