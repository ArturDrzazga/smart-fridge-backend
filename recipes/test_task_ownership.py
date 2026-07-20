from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from recipes.services.task_registry import get_task_owner, register_task

User = get_user_model()


class TaskRegistryTests(APITestCase):
    """Unit tests for the register_task()/get_task_owner() Redis helpers."""

    def test_unregistered_task_id_has_no_owner(self):
        self.assertIsNone(get_task_owner("never-registered-task-id"))

    def test_registered_task_id_returns_correct_owner(self):
        register_task("some-task-id-123", user_id=42)
        self.assertEqual(get_task_owner("some-task-id-123"), "42")


class RecipeSuggestionTaskStatusViewOwnershipTests(APITestCase):
    """
    Tests for GET /api/recipes/suggestions/<task_id>/, specifically the
    fix for: a fake/never-created task_id used to return 200 PENDING
    forever (Celery's AsyncResult can't tell "never existed" apart from
    "not started yet"). Now it should return 404, and so should a
    task_id that belongs to a different user.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="owner@example.com", password="TestPass123"
        )
        self.other_user = User.objects.create_user(
            email="stranger@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)

    def _url(self, task_id):
        return reverse("recipes:recipe-suggestion-status", args=[task_id])

    def test_completely_random_task_id_returns_404(self):
        response = self.client.get(self._url("abc"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_random_valid_looking_uuid_never_created_returns_404(self):
        response = self.client.get(
            self._url("11111111-1111-1111-1111-111111111111")
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_another_users_task_id_returns_404(self):
        register_task("someone-elses-task", user_id=self.other_user.id)

        response = self.client.get(self._url("someone-elses-task"))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("recipes.views.AsyncResult")
    def test_own_task_id_returns_200_with_status(self, mock_async_result):
        register_task("my-own-task", user_id=self.user.id)

        mock_result = MagicMock()
        mock_result.status = "PENDING"
        mock_async_result.return_value = mock_result

        response = self.client.get(self._url("my-own-task"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "PENDING")

    @patch("recipes.views.AsyncResult")
    def test_own_completed_task_includes_result(self, mock_async_result):
        register_task("my-completed-task", user_id=self.user.id)

        mock_result = MagicMock()
        mock_result.status = "SUCCESS"
        mock_result.result = {"recipes": []}
        mock_async_result.return_value = mock_result

        response = self.client.get(self._url("my-completed-task"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "SUCCESS")
        self.assertEqual(response.data["result"], {"recipes": []})

    def test_requires_authentication(self):
        register_task("some-task", user_id=self.user.id)
        self.client.force_authenticate(user=None)

        response = self.client.get(self._url("some-task"))

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class RecipeSuggestionViewRegistersTaskTests(APITestCase):
    """
    Verifies that submitting a suggestion request actually registers
    the returned task_id, so it can be looked up afterwards.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="submitter@example.com", password="TestPass123"
        )
        self.client.force_authenticate(user=self.user)

    @patch("recipes.views.check_daily_limit", return_value=(True, 4))
    @patch("recipes.views.generate_recipe_task")
    def test_submitted_task_is_registered_to_the_requesting_user(
        self, mock_task, mock_limit
    ):
        fake_async_result = MagicMock()
        fake_async_result.id = "brand-new-task-id"
        fake_async_result.status = "PENDING"
        mock_task.delay.return_value = fake_async_result

        response = self.client.post(
            reverse("recipes:recipe-suggestions"),
            {"ingredients": ["eggs"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(
            get_task_owner("brand-new-task-id"), str(self.user.id)
        )