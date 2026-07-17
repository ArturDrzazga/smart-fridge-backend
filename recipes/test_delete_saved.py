from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from recipes.models import Recipe, SavedRecipe

User = get_user_model()


class DeleteSavedRecipeViewTests(APITestCase):
    """Tests for DELETE /api/recipes/saved/<id>/ (SFA-367..369)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="deleter@example.com", password="TestPass123"
        )
        self.other_user = User.objects.create_user(
            email="other-deleter@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)

        self.recipe = Recipe.objects.create(
            title="Toast",
            ingredients=["bread"],
            steps="Toast the bread.",
        )
        self.saved = SavedRecipe.objects.create(user=self.user, recipe=self.recipe)

        self.other_recipe = Recipe.objects.create(
            title="Other's Salad",
            ingredients=["lettuce"],
            steps="Chop it.",
        )
        self.other_saved = SavedRecipe.objects.create(
            user=self.other_user, recipe=self.other_recipe
        )

    def _url(self, saved_id):
        return reverse("recipes:recipe-saved-detail", args=[saved_id])

    def test_delete_own_saved_recipe_returns_204(self):
        response = self.client.delete(self._url(self.saved.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_delete_removes_saved_recipe_row(self):
        self.client.delete(self._url(self.saved.id))
        self.assertFalse(SavedRecipe.objects.filter(id=self.saved.id).exists())

    def test_delete_does_not_remove_underlying_recipe(self):
        self.client.delete(self._url(self.saved.id))
        # Deleting the bookmark should not delete the shared Recipe row.
        self.assertTrue(Recipe.objects.filter(id=self.recipe.id).exists())

    def test_recipe_no_longer_in_saved_list_after_delete(self):
        self.client.delete(self._url(self.saved.id))

        list_response = self.client.get(reverse("recipes:recipe-saved-list"))
        titles = [r["title"] for r in list_response.data]
        self.assertNotIn("Toast", titles)

    def test_delete_another_users_saved_recipe_returns_404(self):
        response = self.client.delete(self._url(self.other_saved.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # And it must NOT have been deleted.
        self.assertTrue(SavedRecipe.objects.filter(id=self.other_saved.id).exists())

    def test_delete_nonexistent_id_returns_404(self):
        response = self.client.delete(self._url(999999))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.delete(self._url(self.saved.id))
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_deleting_twice_returns_404_second_time(self):
        first = self.client.delete(self._url(self.saved.id))
        second = self.client.delete(self._url(self.saved.id))

        self.assertEqual(first.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(second.status_code, status.HTTP_404_NOT_FOUND)