from django.db import models

from config import settings


class Product(models.Model):
    STORAGE_CHOICES = [
        ("fridge", "Fridge"),
        ("freezer", "Freezer"),
    ]

    CATEGORY_CHOICES = [
        ("dairy", "Dairy"),
        ("meat", "Meat & Fish"),
        ("veggies", "Vegetables & Fruits"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="products",
    )
    name = models.CharField(max_length=50)
    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        default="other"
    )
    storage = models.CharField(
        max_length=30,
        choices=STORAGE_CHOICES,
        default="fridge"
    )
    quantity = models.CharField(max_length=10)
    expiry_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.quantity}) - {self.user.email}"


class ShoppingList(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shopping_lists",
    )

    items = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Shopping List for {self.user.email}"
