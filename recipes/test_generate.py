from datetime import date
from unittest.mock import MagicMock, patch

from celery.exceptions import TimeoutError as CeleryTimeoutError
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.test import SimpleTestCase

from recipes.views import _map_to_generate_schema

User = get_user_model()


class FakeRedisPipeline:
    """Minimal fake of a redis pipeline supporting incr/expire/execute."""

    def __init__(self, store, key):
        self.store = store
        self.key = key

    def incr(self, key, amount=1):
        self.store[key] = self.store.get(key, 0) + amount
        return self

    def expire(self, key, seconds):
        return self

    def execute(self):
        return []


class FakeRedisClient:
    """
    Minimal in-memory fake of redis.Redis, sufficient for
    check_and_increment_daily_limit()/get_remaining_requests().
    """

    def __init__(self):
        self.store = {}

    def get(self, key):
        if key not in self.store:
            return None
        return str(self.store[key]).encode()

    def pipeline(self):
        return FakeRedisPipeline(self.store, None)


class RateLimitTests(SimpleTestCase):
    """
    Unit tests for check_and_increment_daily_limit() / get_remaining_requests(),
    using a fake in-memory Redis client so tests don't depend on / pollute
    the real Redis instance.
    """

    def setUp(self):
        self.fake_client = FakeRedisClient()
        patcher = patch(
            "recipes.services.rate_limit._get_redis_client",
            return_value=self.fake_client,
        )
        self.addCleanup(patcher.stop)
        patcher.start()

        # Reset the module-level cached client so our patch takes effect.
        import recipes.services.rate_limit as rate_limit_module
        rate_limit_module._redis_client = None

        from recipes.services.rate_limit import check_and_increment_daily_limit, get_remaining_requests
        self.check_and_increment_daily_limit = check_and_increment_daily_limit
        self.get_remaining_requests = get_remaining_requests

    def test_first_request_of_the_day_is_allowed(self):
        allowed = self.check_and_increment_daily_limit(user_id=1, limit=5)
        self.assertTrue(allowed)

    def test_requests_up_to_limit_are_allowed(self):
        for _ in range(5):
            allowed = self.check_and_increment_daily_limit(user_id=2, limit=5)
            self.assertTrue(allowed)

    def test_request_beyond_limit_is_denied(self):
        for _ in range(5):
            self.check_and_increment_daily_limit(user_id=3, limit=5)

        allowed = self.check_and_increment_daily_limit(user_id=3, limit=5)
        self.assertFalse(allowed)

    def test_denied_request_does_not_increment_further(self):
        for _ in range(5):
            self.check_and_increment_daily_limit(user_id=4, limit=5)

        self.check_and_increment_daily_limit(user_id=4, limit=5)
        self.check_and_increment_daily_limit(user_id=4, limit=5)

        remaining = self.get_remaining_requests(user_id=4, limit=5)
        self.assertEqual(remaining, 0)

    def test_different_users_have_independent_limits(self):
        for _ in range(5):
            self.check_and_increment_daily_limit(user_id=5, limit=5)

        # A different user should still be allowed.
        allowed = self.check_and_increment_daily_limit(user_id=6, limit=5)
        self.assertTrue(allowed)

    def test_get_remaining_requests_decreases_correctly(self):
        self.check_and_increment_daily_limit(user_id=7, limit=5)
        self.check_and_increment_daily_limit(user_id=7, limit=5)
        remaining = self.get_remaining_requests(user_id=7, limit=5)
        self.assertEqual(remaining, 3)


class MapToGenerateSchemaTests(SimpleTestCase):
    """
    Unit tests for _map_to_generate_schema(), which converts the internal
    Gemini result shape into the simplified {title, ingredients, steps}
    schema required by POST /api/recipes/generate/.
    """

    def test_maps_fields_correctly(self):
        gemini_result = {
            "recipes": [
                {
                    "title": "Cheesy Pasta",
                    "ingredients_used": ["pasta", "cheese"],
                    "missing_ingredients": ["salt", "pepper"],
                    "instructions": ["Boil pasta.", "Add cheese."],
                    "prep_time_minutes": 15,
                }
            ]
        }
        mapped = _map_to_generate_schema(gemini_result)
        self.assertEqual(len(mapped["recipes"]), 1)
        recipe = mapped["recipes"][0]
        self.assertEqual(recipe["title"], "Cheesy Pasta")
        self.assertEqual(recipe["ingredients"], ["pasta", "cheese", "salt", "pepper"])
        self.assertEqual(recipe["steps"], ["Boil pasta.", "Add cheese."])
        self.assertNotIn("prep_time_minutes", recipe)
        self.assertNotIn("ingredients_used", recipe)
        self.assertNotIn("missing_ingredients", recipe)
        self.assertNotIn("instructions", recipe)

    def test_handles_empty_recipes_list(self):
        mapped = _map_to_generate_schema({"recipes": []})
        self.assertEqual(mapped, {"recipes": []})

    def test_handles_multiple_recipes(self):
        gemini_result = {
            "recipes": [
                {"title": "A", "ingredients_used": ["x"], "missing_ingredients": [], "instructions": ["step1"]},
                {"title": "B", "ingredients_used": ["y"], "missing_ingredients": ["z"], "instructions": ["step2"]},
            ]
        }
        mapped = _map_to_generate_schema(gemini_result)
        self.assertEqual(len(mapped["recipes"]), 2)
        self.assertEqual(mapped["recipes"][1]["ingredients"], ["y", "z"])


class RecipeGenerateViewTests(APITestCase):
    """
    Integration tests for POST /api/recipes/generate/, covering the
    success path, rate limiting (429), and Gemini failure/timeout (503).
    Celery and Gemini calls are mocked so these tests run instantly and
    don't require a live worker or API key.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="generate-test@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("recipes:recipe-generate")

    @patch("recipes.views.check_and_increment_daily_limit", return_value=True)
    @patch("recipes.views.generate_recipe_suggestions_task")
    def test_successful_generation_returns_200_with_mapped_schema(
        self, mock_task, mock_rate_limit
    ):
        fake_async_result = MagicMock()
        fake_async_result.get.return_value = {
            "recipes": [
                {
                    "title": "Omelette",
                    "ingredients_used": ["eggs"],
                    "missing_ingredients": ["salt"],
                    "instructions": ["Whisk eggs.", "Cook in pan."],
                    "prep_time_minutes": 10,
                }
            ]
        }
        mock_task.delay.return_value = fake_async_result

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["recipes"][0]["title"], "Omelette")
        self.assertEqual(response.data["recipes"][0]["ingredients"], ["eggs", "salt"])
        self.assertEqual(
            response.data["recipes"][0]["steps"], ["Whisk eggs.", "Cook in pan."]
        )

    @patch("recipes.views.check_and_increment_daily_limit", return_value=False)
    def test_returns_429_when_daily_limit_reached(self, mock_rate_limit):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("detail", response.data)

    @patch("recipes.views.check_and_increment_daily_limit", return_value=True)
    @patch("recipes.views.generate_recipe_suggestions_task")
    def test_returns_503_on_celery_timeout(self, mock_task, mock_rate_limit):
        fake_async_result = MagicMock()
        fake_async_result.get.side_effect = CeleryTimeoutError()
        mock_task.delay.return_value = fake_async_result

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("detail", response.data)

    @patch("recipes.views.check_and_increment_daily_limit", return_value=True)
    @patch("recipes.views.generate_recipe_suggestions_task")
    def test_returns_503_when_gemini_task_raises(self, mock_task, mock_rate_limit):
        fake_async_result = MagicMock()
        fake_async_result.get.side_effect = Exception("Gemini API error")
        mock_task.delay.return_value = fake_async_result

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("detail", response.data)

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )