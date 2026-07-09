"""
Prompt template and builder for Gemini-based recipe suggestions.

The prompt template is stored as a module-level constant (RECIPE_PROMPT_TEMPLATE)
so it can be reused, tested, and documented independently of the API call logic
in gemini_service.py.

build_recipe_prompt() accepts a dynamic ingredient list and prioritizes
ingredients that are closer to their expiry date, so that Gemini favors
recipes that help reduce food waste.
"""

from datetime import date, datetime


RECIPE_PROMPT_TEMPLATE = """You are a cooking assistant helping reduce food waste.

{ingredients_section}

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
- Strongly prefer recipes that use ingredients expiring soon (listed as
  "expires in N day(s)" below), to help reduce food waste
- If the ingredient list is empty, return {{"recipes": []}} and do not invent
  ingredients or recipes
- If only one ingredient is provided, suggest simple recipes built primarily
  around that single ingredient, using common pantry staples (salt, pepper,
  oil, water) as needed
"""


def _normalize_ingredient(item):
    """
    Normalize a single ingredient entry into a (name, expiry_date) tuple.

    Accepts either:
      - a plain string, e.g. "eggs"                     -> ("eggs", None)
      - a dict, e.g. {"name": "eggs", "expiry_date": ...} -> ("eggs", date|None)

    expiry_date may be a date/datetime object, an ISO date string
    ("YYYY-MM-DD"), or None/missing.
    """
    if isinstance(item, str):
        return item, None

    name = item.get("name")
    expiry_raw = item.get("expiry_date")

    if expiry_raw is None:
        return name, None

    if isinstance(expiry_raw, (date, datetime)):
        expiry = expiry_raw.date() if isinstance(expiry_raw, datetime) else expiry_raw
    else:
        try:
            expiry = datetime.strptime(str(expiry_raw), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            expiry = None

    return name, expiry


def build_recipe_prompt(ingredients, today=None):
    """
    Build the full Gemini prompt for a given list of ingredients.

    Args:
        ingredients: list of ingredient names (str) or dicts with
            "name" and optional "expiry_date" keys.
        today: optional date to use as "now" reference (mainly for tests).
            Defaults to date.today().

    Returns:
        A formatted prompt string ready to send to the Gemini API.
    """
    today = today or date.today()

    if not ingredients:
        ingredients_section = (
            "No ingredients are currently available in the fridge."
        )
        return RECIPE_PROMPT_TEMPLATE.format(ingredients_section=ingredients_section)

    normalized = [_normalize_ingredient(item) for item in ingredients]

    def sort_key(entry):
        _, expiry = entry
        if expiry is None:
            return (1, 0)
        return (0, (expiry - today).days)

    normalized.sort(key=sort_key)

    lines = ["Available ingredients (sorted by urgency, soonest-expiring first):"]
    for name, expiry in normalized:
        if expiry is None:
            lines.append(f"- {name} (no expiry date set)")
        else:
            days_left = (expiry - today).days
            if days_left < 0:
                lines.append(f"- {name} (expired {abs(days_left)} day(s) ago)")
            elif days_left == 0:
                lines.append(f"- {name} (expires today)")
            else:
                lines.append(f"- {name} (expires in {days_left} day(s))")

    ingredients_section = "\n".join(lines)
    return RECIPE_PROMPT_TEMPLATE.format(ingredients_section=ingredients_section)