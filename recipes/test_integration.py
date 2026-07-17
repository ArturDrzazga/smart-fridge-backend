"""
Integration tests for the full recipe generation flow.

Unlike the unit tests in recipes/tests.py (which mock at the view/task
boundary), these tests exercise the real chain:

    HTTP request -> RecipeGenerateView -> rate limiter (real Redis)
    -> Celery task (run eagerly, in-process) -> prompt builder
    -> gemini_service.generate_recipe_suggestions -> response mapping

Only the actual network call to Gemini is mocked (the low-level client
returned by gemini_service._get_client) - no real API calls are made.
"""

from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from config.celery import app as celery_app
from fridge.models import Product
from recipes.models import Recipe
from recipes.services.rate_limit import _get_redis_client

User = get_user_model()


def _clear_daily_limit_key(user_id):
    """
    Deletes any leftover rate-limit counter for this user/day in Redis,
    so repeated test runs (e.g. running the suite twice on the same
    day) don't inherit stale state from a previous run.
    """
    key = f"recipe_generate_limit:{user_id}:{date.today().isoformat()}"
    _get_redis_client().delete(key)


class RecipeGenerationIntegrationTests(APITestCase):
    """
    Full end-to-end tests for POST /api/recipes/generate/, using a real
    (eagerly-executed) Celery task and real rate limiting, with only
    the Gemini network call mocked.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Force Celery tasks to run synchronously, in-process, during
        # these tests - no real broker/worker round-trip needed.
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True

    def setUp(self):
        self.user = User.objects.create_user(
            email="integration@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("recipes:recipe-generate")
        _clear_daily_limit_key(self.user.id)

    def _mock_gemini_response(self, mock_get_client, response_text):
        mock_response = type("MockResponse", (), {"text": response_text})()
        mock_client = mock_get_client.return_value
        mock_client.models.generate_content.return_value = mock_response

    @patch("recipes.services.gemini_service._get_client")
    def test_generate_recipe_end_to_end_with_mocked_gemini(self, mock_get_client):
        Product.objects.create(
            user=self.user,
            name="eggs",
            quantity="6",
            expiry_date=date.today() + timedelta(days=5),
        )

        self._mock_gemini_response(
            mock_get_client,
            '{"recipes": [{"title": "Simple Omelette", '
            '"ingredients_used": ["eggs"], "missing_ingredients": ["salt"], '
            '"instructions": ["Whisk eggs.", "Cook in pan."], '
            '"prep_time_minutes": 10}]}',
        )

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["recipes"]), 1)
        recipe = response.data["recipes"][0]
        self.assertEqual(recipe["title"], "Simple Omelette")
        self.assertEqual(recipe["ingredients"], ["eggs", "salt"])
        self.assertEqual(recipe["steps"], ["Whisk eggs.", "Cook in pan."])

    @patch("recipes.services.gemini_service._get_client")
    def test_daily_limit_enforcement_5_pass_6th_blocked(self, mock_get_client):
        self._mock_gemini_response(mock_get_client, '{"recipes": []}')

        for i in range(5):
            response = self.client.post(self.url)
            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK,
                f"Request {i + 1}/5 should have succeeded, got {response.status_code}",
            )

        sixth_response = self.client.post(self.url)
        self.assertEqual(
            sixth_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS
        )
        self.assertIn("detail", sixth_response.data)


class SaveRetrieveDeleteFlowIntegrationTests(APITestCase):
    """
    Integration test for the full lifecycle of a saved recipe: save it,
    retrieve it via the list endpoint, delete it, and confirm it's gone.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="flow@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)

        self.recipe = Recipe.objects.create(
            title="Flow Test Pancakes",
            ingredients=["flour", "eggs", "milk"],
            steps="Mix ingredients.\nCook on griddle.",
        )

    def test_full_save_retrieve_delete_flow(self):
        # 1. Save the recipe
        save_response = self.client.post(
            reverse("recipes:recipe-save"),
            {"recipe_id": self.recipe.id},
            format="json",
        )
        self.assertEqual(save_response.status_code, status.HTTP_201_CREATED)
        saved_id = save_response.data["id"]

        # 2. Retrieve it via the saved recipes list
        list_response = self.client.get(reverse("recipes:recipe-saved-list"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        titles = [r["title"] for r in list_response.data]
        self.assertIn("Flow Test Pancakes", titles)

        # 3. Delete it
        delete_response = self.client.delete(
            reverse("recipes:recipe-saved-detail", args=[saved_id])
        )
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

        # 4. Confirm it's gone from the saved list
        list_after_delete = self.client.get(reverse("recipes:recipe-saved-list"))
        titles_after = [r["title"] for r in list_after_delete.data]
        self.assertNotIn("Flow Test Pancakes", titles_after)

    def test_saving_after_deleting_succeeds_again(self):
        save_response = self.client.post(
            reverse("recipes:recipe-save"),
            {"recipe_id": self.recipe.id},
            format="json",
        )
        saved_id = save_response.data["id"]

        self.client.delete(reverse("recipes:recipe-saved-detail", args=[saved_id]))

        # The unique_together constraint is on (user, recipe); since the
        # old SavedRecipe row was deleted, saving again should succeed
        # rather than returning 400.
        second_save = self.client.post(
            reverse("recipes:recipe-save"),
            {"recipe_id": self.recipe.id},
            format="json",
        )
        self.assertEqual(second_save.status_code, status.HTTP_201_CREATED)