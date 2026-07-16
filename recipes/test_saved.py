from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from recipes.models import Recipe, SavedRecipe

User = get_user_model()


class SaveRecipeViewTests(APITestCase):
    """
    Tests for POST /api/recipes/save/ (SFA-356..360).
    The client saves an *existing* recipe by id; the endpoint does not
    create new Recipe rows.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="saver@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("recipes:recipe-save")
        self.recipe = Recipe.objects.create(
            title="Cheesy Omelette",
            ingredients=["eggs", "cheese", "salt"],
            steps="Whisk eggs.\nAdd cheese.\nCook in pan.",
        )

    def test_save_existing_recipe_returns_201_with_ids(self):
        response = self.client.post(
            self.url, {"recipe_id": self.recipe.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user_id"], self.user.id)
        self.assertEqual(response.data["recipe_id"], self.recipe.id)
        self.assertIn("id", response.data)

    def test_save_creates_saved_recipe_row(self):
        self.client.post(self.url, {"recipe_id": self.recipe.id}, format="json")

        self.assertEqual(SavedRecipe.objects.count(), 1)
        saved = SavedRecipe.objects.first()
        self.assertEqual(saved.user, self.user)
        self.assertEqual(saved.recipe, self.recipe)

    def test_saving_same_recipe_twice_returns_400(self):
        self.client.post(self.url, {"recipe_id": self.recipe.id}, format="json")
        response = self.client.post(
            self.url, {"recipe_id": self.recipe.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Only the first save should have gone through.
        self.assertEqual(SavedRecipe.objects.count(), 1)

    def test_saving_nonexistent_recipe_returns_404(self):
        response = self.client.post(self.url, {"recipe_id": 999999}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_save_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.url, {"recipe_id": self.recipe.id}, format="json"
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_missing_recipe_id_returns_400(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_different_users_can_save_the_same_recipe(self):
        other_user = User.objects.create_user(
            email="other-saver@example.com", password="TestPass123"
        )
        self.client.post(self.url, {"recipe_id": self.recipe.id}, format="json")

        self.client.force_authenticate(user=other_user)
        response = self.client.post(
            self.url, {"recipe_id": self.recipe.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SavedRecipe.objects.count(), 2)


class SavedRecipeListViewTests(APITestCase):
    """Tests for GET /api/recipes/saved/ (SFA-362..365)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="lister@example.com", password="TestPass123"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("recipes:recipe-saved-list")

    def _save_recipe_for(self, user, title, ingredients, steps_list):
        recipe = Recipe.objects.create(
            title=title,
            ingredients=ingredients,
            steps="\n".join(steps_list),
        )
        SavedRecipe.objects.create(user=user, recipe=recipe)
        return recipe

    def test_returns_empty_array_when_no_saved_recipes(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_returns_saved_recipes_with_full_details(self):
        self._save_recipe_for(
            self.user, "Pancakes", ["flour", "eggs", "milk"],
            ["Mix ingredients.", "Cook on griddle."],
        )
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        recipe_data = response.data[0]
        self.assertEqual(recipe_data["title"], "Pancakes")
        self.assertEqual(recipe_data["ingredients"], ["flour", "eggs", "milk"])
        self.assertEqual(
            recipe_data["steps"], ["Mix ingredients.", "Cook on griddle."]
        )

    def test_only_returns_current_users_saved_recipes(self):
        self._save_recipe_for(self.user, "My Recipe", ["a"], ["step"])
        self._save_recipe_for(
            self.other_user, "Someone Else's Recipe", ["b"], ["step"]
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [r["title"] for r in response.data]
        self.assertIn("My Recipe", titles)
        self.assertNotIn("Someone Else's Recipe", titles)

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_multiple_saved_recipes_all_returned(self):
        self._save_recipe_for(self.user, "Recipe A", ["a"], ["step a"])
        self._save_recipe_for(self.user, "Recipe B", ["b"], ["step b"])
        self._save_recipe_for(self.user, "Recipe C", ["c"], ["step c"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)