from datetime import date

from django.test import SimpleTestCase

from recipes.services.prompts import build_recipe_prompt, RECIPE_PROMPT_TEMPLATE


class BuildRecipePromptTests(SimpleTestCase):
    """
    Unit tests for build_recipe_prompt(), covering the combinations
    required by SFA-134 (5+ different ingredient combinations) plus the
    edge cases from the ticket's acceptance criteria (empty fridge,
    single ingredient).
    """

    def setUp(self):
        self.today = date(2026, 7, 9)

    # --- Edge cases from acceptance criteria -----------------------------

    def test_empty_ingredient_list(self):
        prompt = build_recipe_prompt([], today=self.today)
        self.assertIn("No ingredients are currently available", prompt)
        self.assertIn('{"recipes": []}', prompt)

    def test_single_ingredient_no_expiry(self):
        prompt = build_recipe_prompt(["eggs"], today=self.today)
        self.assertIn("- eggs (no expiry date set)", prompt)
        self.assertIn("single ingredient", prompt)

    # --- 5+ different ingredient combinations -----------------------------

    def test_plain_string_list_backward_compatible(self):
        prompt = build_recipe_prompt(
            ["eggs", "tomatoes", "cheese"], today=self.today
        )
        self.assertIn("- eggs (no expiry date set)", prompt)
        self.assertIn("- tomatoes (no expiry date set)", prompt)
        self.assertIn("- cheese (no expiry date set)", prompt)

    def test_two_ingredients_with_expiry_dates(self):
        ingredients = [
            {"name": "milk", "expiry_date": "2026-07-10"},
            {"name": "flour", "expiry_date": "2026-09-01"},
        ]
        prompt = build_recipe_prompt(ingredients, today=self.today)
        self.assertIn("milk (expires in 1 day(s))", prompt)
        self.assertIn("flour (expires in 54 day(s))", prompt)

    def test_soonest_expiring_ingredient_listed_first(self):
        ingredients = [
            {"name": "cheese", "expiry_date": "2026-07-20"},
            {"name": "spinach", "expiry_date": "2026-07-10"},
            {"name": "chicken breast", "expiry_date": "2026-07-09"},
        ]
        prompt = build_recipe_prompt(ingredients, today=self.today)
        chicken_pos = prompt.find("chicken breast")
        spinach_pos = prompt.find("spinach")
        cheese_pos = prompt.find("cheese")
        self.assertTrue(chicken_pos < spinach_pos < cheese_pos)

    def test_mixed_strings_and_dicts_with_and_without_expiry(self):
        ingredients = [
            "pasta",
            {"name": "milk", "expiry_date": "2026-07-05"},
            "onion",
            {"name": "spinach", "expiry_date": "2026-07-10"},
        ]
        prompt = build_recipe_prompt(ingredients, today=self.today)
        # Item with the earliest (even past) expiry should appear first
        milk_pos = prompt.find("milk")
        spinach_pos = prompt.find("spinach")
        pasta_pos = prompt.find("pasta")
        self.assertTrue(milk_pos < spinach_pos < pasta_pos)
        self.assertIn("no expiry date set", prompt)

    def test_expired_ingredient_reported_correctly(self):
        ingredients = [{"name": "milk", "expiry_date": "2026-07-05"}]
        prompt = build_recipe_prompt(ingredients, today=self.today)
        self.assertIn("milk (expired 4 day(s) ago)", prompt)

    def test_ingredient_expiring_today(self):
        ingredients = [{"name": "chicken breast", "expiry_date": "2026-07-09"}]
        prompt = build_recipe_prompt(ingredients, today=self.today)
        self.assertIn("chicken breast (expires today)", prompt)

    def test_large_realistic_fridge_combination(self):
        ingredients = [
            {"name": "eggs", "expiry_date": "2026-07-15"},
            {"name": "tomatoes", "expiry_date": "2026-07-11"},
            {"name": "cheese", "expiry_date": "2026-07-25"},
            "onion",
            "garlic",
            {"name": "pasta", "expiry_date": None},
            {"name": "chicken breast", "expiry_date": "2026-07-10"},
            {"name": "spinach", "expiry_date": "2026-07-09"},
            "milk",
            "butter",
        ]
        prompt = build_recipe_prompt(ingredients, today=self.today)
        for name in [
            "eggs", "tomatoes", "cheese", "onion", "garlic",
            "pasta", "chicken breast", "spinach", "milk", "butter",
        ]:
            self.assertIn(name, prompt)
        # Soonest-expiring item (spinach, expires today) must be listed first
        first_ingredient_line = prompt.split(
            "Available ingredients (sorted by urgency, soonest-expiring first):\n"
        )[1].split("\n")[0]
        self.assertIn("spinach", first_ingredient_line)

    # --- Template integrity -------------------------------------------

    def test_prompt_always_requests_valid_json_only(self):
        prompt = build_recipe_prompt(["eggs"], today=self.today)
        self.assertIn("Return only JSON", prompt)
        self.assertIn("No markdown", prompt)

    def test_template_constant_has_ingredients_placeholder(self):
        self.assertIn("{ingredients_section}", RECIPE_PROMPT_TEMPLATE)