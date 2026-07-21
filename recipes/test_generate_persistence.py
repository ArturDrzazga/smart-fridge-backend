from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from recipes.models import Recipe, SavedRecipe

User = get_user_model()


class RecipeGenerateViewPersistenceTests(APITestCase):
    """
    Tests for the fix reported by Oleksandr: POST /api/recipes/generate/
    previously returned recipes with no id at all, so there was no
    legitimate recipe_id a client could pass to POST /api/recipes/save/.
    Generated recipes must now be persisted, with their id included in
    the response.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="persist-test@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("recipes:recipe-generate")

    @patch("recipes.views.check_and_increment_daily_limit", return_value=True)
    @patch("recipes.views.generate_recipe_suggestions_task")
    def test_generated_recipes_include_an_id(self, mock_task, mock_rate_limit):
        fake_async_result = MagicMock()
        fake_async_result.get.return_value = {
            "recipes": [
                {
                    "title": "Omelette",
                    "ingredients_used": ["eggs"],
                    "missing_ingredients": ["salt"],
                    "instructions": ["Whisk eggs.", "Cook in pan."],
                }
            ]
        }
        mock_task.delay.return_value = fake_async_result

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recipe = response.data["recipes"][0]
        self.assertIn("id", recipe)
        self.assertIsNotNone(recipe["id"])

    @patch("recipes.views.check_and_increment_daily_limit", return_value=True)
    @patch("recipes.views.generate_recipe_suggestions_task")
    def test_generated_recipes_are_persisted_to_the_database(
        self, mock_task, mock_rate_limit
    ):
        fake_async_result = MagicMock()
        fake_async_result.get.return_value = {
            "recipes": [
                {
                    "title": "Pancakes",
                    "ingredients_used": ["flour", "eggs"],
                    "missing_ingredients": ["milk"],
                    "instructions": ["Mix.", "Cook."],
                }
            ]
        }
        mock_task.delay.return_value = fake_async_result

        response = self.client.post(self.url)

        recipe_id = response.data["recipes"][0]["id"]
        self.assertTrue(Recipe.objects.filter(id=recipe_id).exists())
        saved_recipe = Recipe.objects.get(id=recipe_id)
        self.assertEqual(saved_recipe.title, "Pancakes")
        self.assertEqual(saved_recipe.ingredients, ["flour", "eggs", "milk"])

    @patch("recipes.views.check_and_increment_daily_limit", return_value=True)
    @patch("recipes.views.generate_recipe_suggestions_task")
    def test_multiple_generated_recipes_each_get_their_own_id(
        self, mock_task, mock_rate_limit
    ):
        fake_async_result = MagicMock()
        fake_async_result.get.return_value = {
            "recipes": [
                {"title": "A", "ingredients_used": ["x"], "missing_ingredients": [], "instructions": ["step1"]},
                {"title": "B", "ingredients_used": ["y"], "missing_ingredients": [], "instructions": ["step2"]},
            ]
        }
        mock_task.delay.return_value = fake_async_result

        response = self.client.post(self.url)

        ids = [r["id"] for r in response.data["recipes"]]
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)  # both ids are distinct

    @patch("recipes.views.check_and_increment_daily_limit", return_value=True)
    @patch("recipes.views.generate_recipe_suggestions_task")
    def test_generated_recipe_id_can_immediately_be_saved(
        self, mock_task, mock_rate_limit
    ):
        """
        End-to-end regression test for Oleksandr's exact scenario:
        generate a recipe, then immediately save it using the id from
        the generate response.
        """
        fake_async_result = MagicMock()
        fake_async_result.get.return_value = {
            "recipes": [
                {
                    "title": "Cheese Toast",
                    "ingredients_used": ["bread", "cheese"],
                    "missing_ingredients": [],
                    "instructions": ["Toast.", "Add cheese."],
                }
            ]
        }
        mock_task.delay.return_value = fake_async_result

        generate_response = self.client.post(self.url)
        recipe_id = generate_response.data["recipes"][0]["id"]

        save_response = self.client.post(
            reverse("recipes:recipe-save"),
            {"recipe_id": recipe_id},
            format="json",
        )

        self.assertEqual(save_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(save_response.data["recipe_id"], recipe_id)
        self.assertTrue(
            SavedRecipe.objects.filter(user=self.user, recipe_id=recipe_id).exists()
        )