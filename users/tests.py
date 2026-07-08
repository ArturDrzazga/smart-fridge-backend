from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User


class RegisterEndpointTests(APITestCase):
    """
    Tests for POST /api/auth/register/

    Covers acceptance criteria:
    - Accepts email (unique) + password (min 8 chars)
    - Password hashed via PBKDF2 before saving to DB
    - Returns 201: { id, email, created_at } on success
    - Returns 400 if email already registered
    - Returns 400 if password shorter than 8 characters
    """

    def setUp(self):
        self.url = reverse("register")
        self.valid_payload = {
            "email": "newuser@example.com",
            "password": "SecurePass123",
        }

    def test_register_with_valid_data_returns_201(self):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_register_response_contains_expected_fields(self):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertIn("id", response.data)
        self.assertIn("email", response.data)
        self.assertIn("created_at", response.data)
        self.assertEqual(response.data["email"], self.valid_payload["email"])

    def test_register_response_does_not_leak_password(self):
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertNotIn("password", response.data)

    def test_user_is_created_in_database(self):
        self.client.post(self.url, self.valid_payload, format="json")

        self.assertTrue(
            User.objects.filter(email=self.valid_payload["email"]).exists()
        )

    def test_password_is_hashed_with_pbkdf2(self):
        self.client.post(self.url, self.valid_payload, format="json")

        user = User.objects.get(email=self.valid_payload["email"])

        # Password must not be stored in plain text
        self.assertNotEqual(user.password, self.valid_payload["password"])
        # Django's default hasher is PBKDF2 (algorithm prefix "pbkdf2_")
        self.assertTrue(user.password.startswith("pbkdf2_"))
        # Sanity check: the stored hash should validate against the raw password
        self.assertTrue(user.check_password(self.valid_payload["password"]))

    def test_register_with_duplicate_email_returns_400(self):
        User.objects.create_user(
            email=self.valid_payload["email"], password="AnotherPass123"
        )

        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_with_short_password_returns_400(self):
        payload = {"email": "shortpass@example.com", "password": "abc123"}

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_register_with_missing_email_returns_400(self):
        payload = {"password": "SecurePass123"}

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_with_missing_password_returns_400(self):
        payload = {"email": "noPassword@example.com"}

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_with_invalid_email_format_returns_400(self):
        payload = {"email": "not-an-email", "password": "SecurePass123"}

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_is_normalized_to_lowercase(self):
        payload = {"email": "MixedCase@Example.com", "password": "SecurePass123"}

        self.client.post(self.url, payload, format="json")

        self.assertTrue(
            User.objects.filter(email="mixedcase@example.com").exists()
        )