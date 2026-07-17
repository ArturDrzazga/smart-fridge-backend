from datetime import date, timedelta

from django.test import SimpleTestCase

from fridge.models import Product
from recipes.services.product_prompt import build_prompt_from_products


def _make_product(name, expiry_date=None):
    """
    Builds an in-memory (unsaved) Product instance, sufficient for
    testing build_prompt_from_products() without touching the database.
    """
    return Product(name=name, expiry_date=expiry_date)


class BuildPromptFromProductsTests(SimpleTestCase):
    """
    Unit tests for build_prompt_from_products(), which accepts a list of
    Product model instances directly (as required by the ticket), and
    delegates to build_recipe_prompt() to reuse the team's agreed-upon
    "rich" JSON schema (ingredients_used, missing_ingredients,
    instructions, prep_time_minutes).
    """

    def setUp(self):
        self.today = date(2026, 7, 16)

    # --- Edge cases from acceptance criteria -----------------------------

    def test_empty_fridge(self):
        prompt = build_prompt_from_products([], today=self.today)
        self.assertIn("No ingredients are currently available", prompt)
        self.assertIn('{"recipes": []}', prompt)

    def test_single_product(self):
        products = [_make_product("eggs")]
        prompt = build_prompt_from_products(products, today=self.today)
        self.assertIn("- eggs (no expiry date set)", prompt)
        self.assertIn("single ingredient", prompt)

    # --- 3+ product combinations -------------------------------------

    def test_three_products_with_different_expiry_dates(self):
        products = [
            _make_product("cheese", self.today + timedelta(days=20)),
            _make_product("spinach", self.today + timedelta(days=1)),
            _make_product("milk", self.today + timedelta(days=10)),
        ]
        prompt = build_prompt_from_products(products, today=self.today)

        spinach_pos = prompt.find("spinach")
        milk_pos = prompt.find("milk")
        cheese_pos = prompt.find("cheese")
        self.assertTrue(spinach_pos < milk_pos < cheese_pos)

    def test_mixed_products_with_and_without_expiry(self):
        products = [
            _make_product("pasta", None),
            _make_product("chicken breast", self.today + timedelta(days=2)),
            _make_product("onion", None),
        ]
        prompt = build_prompt_from_products(products, today=self.today)

        self.assertIn("chicken breast (expires in 2 day(s))", prompt)
        self.assertIn("pasta (no expiry date set)", prompt)
        self.assertIn("onion (no expiry date set)", prompt)
        chicken_pos = prompt.find("chicken breast")
        pasta_pos = prompt.find("pasta")
        self.assertTrue(chicken_pos < pasta_pos)

    def test_expired_product_reported_correctly(self):
        products = [_make_product("yogurt", self.today - timedelta(days=3))]
        prompt = build_prompt_from_products(products, today=self.today)
        self.assertIn("yogurt (expired 3 day(s) ago)", prompt)

    def test_product_expiring_today(self):
        products = [_make_product("bread", self.today)]
        prompt = build_prompt_from_products(products, today=self.today)
        self.assertIn("bread (expires today)", prompt)

    def test_large_realistic_combination(self):
        products = [
            _make_product("eggs", self.today + timedelta(days=6)),
            _make_product("tomatoes", self.today + timedelta(days=2)),
            _make_product("cheese", self.today + timedelta(days=16)),
            _make_product("onion", None),
            _make_product("garlic", None),
            _make_product("chicken breast", self.today + timedelta(days=1)),
            _make_product("spinach", self.today),
        ]
        prompt = build_prompt_from_products(products, today=self.today)

        for name in [
            "eggs", "tomatoes", "cheese", "onion", "garlic",
            "chicken breast", "spinach",
        ]:
            self.assertIn(name, prompt)

        first_line = prompt.split(
            "Available ingredients (sorted by urgency, soonest-expiring first):\n"
        )[1].split("\n")[0]
        self.assertIn("spinach", first_line)

    # --- Schema / template integrity -----------------------------------

    def test_prompt_uses_the_teams_rich_schema(self):
        products = [_make_product("eggs")]
        prompt = build_prompt_from_products(products, today=self.today)
        self.assertIn('"title": "string"', prompt)
        self.assertIn('"ingredients_used": ["string"]', prompt)
        self.assertIn('"missing_ingredients": ["string"]', prompt)
        self.assertIn('"instructions": ["string"]', prompt)
        self.assertIn('"prep_time_minutes": 0', prompt)

    def test_prompt_always_requests_valid_json_only(self):
        products = [_make_product("eggs")]
        prompt = build_prompt_from_products(products, today=self.today)
        self.assertIn("Return only JSON", prompt)
        self.assertIn("No markdown", prompt)