from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from fridge.models import Product

User = get_user_model()


class ProductViewSetTestCase(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            email="user1@example.com",
            password="Password123!"
        )
        self.user2 = User.objects.create_user(
            email="user2@example.com",
            password="Password123!"
        )

        self.list_create_url = reverse("fridge:product-list")

        self.product1 = Product.objects.create(
            user=self.user1,
            name="Milk",
            category="dairy",
            storage="fridge",
            quantity="1L",
            expiry_date=date.today() + timedelta(days=5)
        )

    def _get_detail_url(self, product_id):
        return reverse("fridge:product-detail", kwargs={"pk": product_id})

    def test_unauthenticated_user_cannot_access_products(self):
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_sees_only_own_products(self):
        Product.objects.create(
            user=self.user2,
            name="Cheese",
            category="dairy",
            storage="fridge",
            quantity="200g",
            expiry_date=date.today() + timedelta(days=10)
        )

        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.list_create_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Milk")

    def test_user_cannot_get_other_users_product_detail(self):
        product_user2 = Product.objects.create(
            user=self.user2,
            name="Bread",
            category="other",
            storage="fridge",
            quantity="1",
            expiry_date=date.today()
        )

        self.client.force_authenticate(user=self.user1)
        url = self._get_detail_url(product_user2.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


    def test_create_product_success(self):
        self.client.force_authenticate(user=self.user1)
        payload = {
            "name": "Chicken Breast",
            "category": "meat",
            "storage": "freezer",
            "quantity": "500g",
            "expiry_date": (date.today() + timedelta(days=30)).isoformat()
        }

        response = self.client.post(self.list_create_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Product.objects.filter(user=self.user1).count(), 2)

        new_product = Product.objects.get(id=response.data["id"])
        self.assertEqual(new_product.user, self.user1)

    def test_update_product_success(self):
        self.client.force_authenticate(user=self.user1)
        url = self._get_detail_url(self.product1.id)
        payload = {
            "name": "Oat Milk",
            "category": "dairy",
            "storage": "fridge",
            "quantity": "2L",
            "expiry_date": self.product1.expiry_date.isoformat()
        }

        response = self.client.put(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.name, "Oat Milk")

    def test_delete_product_success(self):
        self.client.force_authenticate(user=self.user1)
        url = self._get_detail_url(self.product1.id)

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Product.objects.filter(id=self.product1.id).exists())

    def test_filter_products_by_category_and_storage(self):
        self.client.force_authenticate(user=self.user1)

        Product.objects.create(
            user=self.user1,
            name="Frozen Peas",
            category="veggies",
            storage="freezer",
            quantity="400g",
            expiry_date=date.today() + timedelta(days=100)
        )

        response = self.client.get(f"{self.list_create_url}?storage=freezer")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Frozen Peas")

    def test_ordering_by_expiry_date(self):
        self.client.force_authenticate(user=self.user1)

        sooner_product = Product.objects.create(
            user=self.user1,
            name="Yogurt",
            category="dairy",
            storage="fridge",
            quantity="1",
            expiry_date=date.today() + timedelta(days=1)
        )

        response = self.client.get(f"{self.list_create_url}?ordering=expiry_date")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["name"], sooner_product.name)