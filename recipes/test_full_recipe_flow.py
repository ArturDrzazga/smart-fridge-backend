"""
Integration tests covering the full recipe flow:
generate -> save -> retrieve -> delete.

Only the Gemini network call is mocked (recipes.services.gemini_service
._get_client) - no real API calls are made anywhere in this file. Every
other layer (view, rate limiter, Celery task run eagerly, DB) runs for
real, so these tests exercise the actual integration between endpoints,
not just each one in isolation.

Maps directly to the ticket's subtasks:
    SFA-572 - test_generate_recipe_with_mock_gemini_response
    SFA-573 - test_daily_limit_enforcement_5_pass_6th_blocked
    SFA-574 - test_save_recipe_then_duplicate_returns_400
    SFA-575 - test_get_saved_recipes_returns_correct_recipes
    SFA-576 - test_delete_own_recipe_and_other_users_recipe
"""

from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from config.celery import app as celery_app
from fridge.models import Product
from recipes.models import Recipe, SavedRecipe
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


def _mock_gemini_response(mock_get_client, response_text):
    mock_response = type("MockResponse", (), {"text": response_text})()
    mock_client = mock_get_client.return_value
    mock_client.models.generate_content.return_value = mock_response


class GenerateRecipeIntegrationTests(APITestCase):
    """SFA-572: full generate flow with a mocked Gemini response."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Force Celery tasks to run synchronously, in-process, during
        # these tests - no real broker/worker round-trip needed.
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True

    def setUp(self):
        self.user = User.objects.create_user(
            email="generate-flow@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("recipes:recipe-generate")
        _clear_daily_limit_key(self.user.id)

    @patch("recipes.services.gemini_service._get_client")
    def test_generate_recipe_with_mock_gemini_response(self, mock_get_client):
        Product.objects.create(
            user=self.user,
            name="eggs",
            quantity="6",
            expiry_date=date.today() + timedelta(days=5),
        )

        _mock_gemini_response(
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
        self.assertIn("id", recipe)
        self.assertEqual(recipe["title"], "Simple Omelette")
        self.assertEqual(recipe["ingredients"], ["eggs", "salt"])
        self.assertEqual(recipe["steps"], ["Whisk eggs.", "Cook in pan."])
        # The recipe must actually be persisted, since /save/ depends on it.
        self.assertTrue(Recipe.objects.filter(id=recipe["id"]).exists())


class DailyLimitIntegrationTests(APITestCase):
    """SFA-573: daily limit enforcement - 5 requests pass, 6th is blocked."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True

    def setUp(self):
        self.user = User.objects.create_user(
            email="daily-limit-flow@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("recipes:recipe-generate")
        _clear_daily_limit_key(self.user.id)

    @patch("recipes.services.gemini_service._get_client")
    def test_daily_limit_enforcement_5_pass_6th_blocked(self, mock_get_client):
        _mock_gemini_response(mock_get_client, '{"recipes": []}')

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


class SaveRecipeIntegrationTests(APITestCase):
    """SFA-574: save flow - save succeeds, saving the same recipe again returns 400."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="save-flow@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)
        self.recipe = Recipe.objects.create(
            title="Cheese Toast",
            ingredients=["bread", "cheese"],
            steps="Toast bread.\nAdd cheese.",
        )
        self.save_url = reverse("recipes:recipe-save")

    def test_save_recipe_then_duplicate_returns_400(self):
        first_response = self.client.post(
            self.save_url, {"recipe_id": self.recipe.id}, format="json"
        )
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first_response.data["recipe_id"], self.recipe.id)
        self.assertTrue(
            SavedRecipe.objects.filter(
                user=self.user, recipe=self.recipe
            ).exists()
        )

        duplicate_response = self.client.post(
            self.save_url, {"recipe_id": self.recipe.id}, format="json"
        )
        self.assertEqual(
            duplicate_response.status_code, status.HTTP_400_BAD_REQUEST
        )
        # Still only one SavedRecipe row - the duplicate attempt didn't
        # create a second one.
        self.assertEqual(
            SavedRecipe.objects.filter(
                user=self.user, recipe=self.recipe
            ).count(),
            1,
        )


class GetSavedRecipesIntegrationTests(APITestCase):
    """SFA-575: GET /api/recipes/saved/ returns the correct recipes."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="get-saved-flow@example.com", password="TestPass123"
        )
        self.other_user = User.objects.create_user(
            email="get-saved-other@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)
        self.saved_url = reverse("recipes:recipe-saved-list")

    def _save_recipe_for(self, user, title, ingredients, steps_list):
        recipe = Recipe.objects.create(
            title=title, ingredients=ingredients, steps="\n".join(steps_list)
        )
        SavedRecipe.objects.create(user=user, recipe=recipe)
        return recipe

    def test_get_saved_recipes_returns_correct_recipes(self):
        self._save_recipe_for(
            self.user, "Pancakes", ["flour", "eggs", "milk"],
            ["Mix.", "Cook on griddle."],
        )
        self._save_recipe_for(
            self.user, "Salad", ["lettuce", "tomato"], ["Chop.", "Toss."],
        )
        # A recipe saved by a different user must not show up here.
        self._save_recipe_for(
            self.other_user, "Someone Else's Soup", ["stock"], ["Simmer."],
        )

        response = self.client.get(self.saved_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        titles = {r["title"] for r in response.data}
        self.assertEqual(titles, {"Pancakes", "Salad"})

        pancakes = next(r for r in response.data if r["title"] == "Pancakes")
        self.assertEqual(pancakes["ingredients"], ["flour", "eggs", "milk"])
        self.assertEqual(pancakes["steps"], ["Mix.", "Cook on griddle."])
        self.assertIn("id", pancakes)
        self.assertIn("created_at", pancakes)

    def test_get_saved_recipes_empty_list_when_none_saved(self):
        response = self.client.get(self.saved_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])


class DeleteSavedRecipeIntegrationTests(APITestCase):
    """SFA-576: delete own saved recipe (204) vs another user's (404)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="delete-flow@example.com", password="TestPass123"
        )
        self.other_user = User.objects.create_user(
            email="delete-flow-other@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)

        own_recipe = Recipe.objects.create(
            title="My Soup", ingredients=["stock"], steps="Simmer."
        )
        self.own_saved = SavedRecipe.objects.create(
            user=self.user, recipe=own_recipe
        )

        other_recipe = Recipe.objects.create(
            title="Their Soup", ingredients=["stock"], steps="Simmer."
        )
        self.other_saved = SavedRecipe.objects.create(
            user=self.other_user, recipe=other_recipe
        )

    def _delete_url(self, saved_id):
        return reverse("recipes:recipe-saved-detail", args=[saved_id])

    def test_delete_own_saved_recipe_returns_204(self):
        response = self.client.delete(self._delete_url(self.own_saved.id))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            SavedRecipe.objects.filter(id=self.own_saved.id).exists()
        )

    def test_delete_other_users_saved_recipe_returns_404(self):
        response = self.client.delete(self._delete_url(self.other_saved.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # Must NOT have been deleted.
        self.assertTrue(
            SavedRecipe.objects.filter(id=self.other_saved.id).exists()
        )