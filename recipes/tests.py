from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase
from django.test.testcases import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from recipes.exceptions import GeminiTimeoutError
from recipes.services.parser import parse_gemini_response
from recipes.services.prompts import RECIPE_PROMPT_TEMPLATE, build_recipe_prompt
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from fridge.models import Product
from recipes.services.prompts import build_recipe_prompt, RECIPE_PROMPT_TEMPLATE
from recipes.tasks import _get_user_fridge_ingredients, generate_recipe_suggestions_task

User = get_user_model()


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


class GeminiParserTestCase(TestCase):

    def test_parse_valid_response(self):
        raw_json = """
        {
          "recipes": [
            {
              "title": "Quick Scrambled Eggs",
              "ingredients": ["eggs", "butter"],
              "steps": ["Melt butter.", "Whisk eggs and cook."]
            }
          ]
        }
        """
        result = parse_gemini_response(raw_json)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Quick Scrambled Eggs")
        self.assertEqual(result[0]["ingredients"], ["eggs", "butter"])

    def test_parse_malformed_json_graceful_handling(self):
        bad_json = "{ 'recipes': [ { 'title': 'Broken Recipe'... "
        result = parse_gemini_response(bad_json)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Error generating recipe")
        self.assertIn("invalid recipe structure", result[0]["steps"][0])

    def test_parse_missing_fields_fallback(self):
        missing_fields_json = """
        {
          "recipes": [
            {
              "title": "No Ingredient Salad"
            }
          ]
        }
        """
        result = parse_gemini_response(missing_fields_json)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["ingredients"], [])
        self.assertEqual(result[0]["steps"], ["No instructions provided by AI."])


class GeminiExceptionHandlingTestCase(APITestCase):

    @patch("recipes.views.check_daily_limit")
    def test_gemini_timeout_returns_503(self, mock_limit):
        mock_limit.return_value = (True, 4)

        with patch("recipes.views.generate_recipe_task.delay") as mock_task:
            mock_task.side_effect = GeminiTimeoutError()

            url = reverse("recipes:recipe-suggestions")
            data = {"ingredients": ["eggs"]}

            response = self.client.post(url, data, format="json")

            self.assertEqual(response.status_code, 503)
            self.assertEqual(
                response.data, {"error": "AI service temporarily unavailable"}
            )
class GetUserFridgeIngredientsTests(TestCase):
    """
    Tests for _get_user_fridge_ingredients(), which pulls a user's
    fridge/freezer contents from the database and formats them for the
    Gemini prompt builder.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="fridgeowner@example.com", password="TestPass123"
        )
        self.other_user = User.objects.create_user(
            email="someoneelse@example.com", password="TestPass123"
        )
        self.today = date(2026, 7, 9)

    def test_empty_fridge_returns_empty_list(self):
        result = _get_user_fridge_ingredients(self.user.id)
        self.assertEqual(result, [])

    def test_single_product_returned_with_expiry(self):
        Product.objects.create(
            user=self.user,
            name="eggs",
            quantity="6",
            expiry_date=self.today + timedelta(days=5),
        )
        result = _get_user_fridge_ingredients(self.user.id)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "eggs")
        self.assertEqual(
            result[0]["expiry_date"], (self.today + timedelta(days=5)).isoformat()
        )

    def test_products_sorted_by_soonest_expiry_first(self):
        Product.objects.create(
            user=self.user, name="cheese", quantity="200g",
            expiry_date=self.today + timedelta(days=20),
        )
        Product.objects.create(
            user=self.user, name="spinach", quantity="1 bag",
            expiry_date=self.today + timedelta(days=1),
        )
        Product.objects.create(
            user=self.user, name="milk", quantity="1L",
            expiry_date=self.today + timedelta(days=10),
        )
        result = _get_user_fridge_ingredients(self.user.id)
        names_in_order = [item["name"] for item in result]
        self.assertEqual(names_in_order, ["spinach", "milk", "cheese"])

    def test_only_returns_current_users_products(self):
        Product.objects.create(
            user=self.user, name="eggs", quantity="6",
            expiry_date=self.today + timedelta(days=5),
        )
        Product.objects.create(
            user=self.other_user, name="butter", quantity="250g",
            expiry_date=self.today + timedelta(days=5),
        )
        result = _get_user_fridge_ingredients(self.user.id)
        names = [item["name"] for item in result]
        self.assertIn("eggs", names)
        self.assertNotIn("butter", names)

    def test_expired_product_still_included(self):
        Product.objects.create(
            user=self.user, name="yogurt", quantity="1",
            expiry_date=self.today - timedelta(days=3),
        )
        result = _get_user_fridge_ingredients(self.user.id)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "yogurt")


class GenerateRecipeSuggestionsTaskTests(TestCase):
    """
    Tests for generate_recipe_suggestions_task(), verifying it fetches
    from the database when no explicit ingredient list is given, and
    respects a manually provided list when one is passed.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="tasktest@example.com", password="TestPass123"
        )
        self.today = date(2026, 7, 9)

    @patch("recipes.tasks.generate_recipe_suggestions")
    def test_fetches_from_db_when_no_ingredients_given(self, mock_generate):
        Product.objects.create(
            user=self.user, name="tomatoes", quantity="4",
            expiry_date=self.today + timedelta(days=2),
        )
        mock_generate.return_value = {"recipes": []}

        generate_recipe_suggestions_task.run(self.user.id, None)

        called_ingredients = mock_generate.call_args[0][0]
        self.assertEqual(len(called_ingredients), 1)
        self.assertEqual(called_ingredients[0]["name"], "tomatoes")

    @patch("recipes.tasks.generate_recipe_suggestions")
    def test_uses_manual_ingredients_when_provided(self, mock_generate):
        Product.objects.create(
            user=self.user, name="tomatoes", quantity="4",
            expiry_date=self.today + timedelta(days=2),
        )
        mock_generate.return_value = {"recipes": []}

        manual_list = ["eggs", "cheese"]
        generate_recipe_suggestions_task.run(self.user.id, manual_list)

        called_ingredients = mock_generate.call_args[0][0]
        self.assertEqual(called_ingredients, manual_list)

    @patch("recipes.tasks.generate_recipe_suggestions")
    def test_empty_fridge_calls_generate_with_empty_list(self, mock_generate):
        mock_generate.return_value = {"recipes": []}

        generate_recipe_suggestions_task.run(self.user.id, None)

        called_ingredients = mock_generate.call_args[0][0]
        self.assertEqual(called_ingredients, [])
