from django.db import models

from config import settings


class Recipe(models.Model):
    DIFFICULTY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    title = models.CharField(max_length=255)
    description = models.CharField(max_length=500, null=True, blank=True)
    ingredients = models.JSONField(default=list)
    steps = models.TextField()
    servings = models.PositiveIntegerField(null=True, blank=True)
    prep_time_minutes = models.PositiveIntegerField(null=True, blank=True)
    difficulty = models.CharField(
        max_length=10, choices=DIFFICULTY_CHOICES, null=True, blank=True
    )
    # Stores the Unsplash photo data as a single JSON blob rather than
    # separate columns, since it's always read/written as one unit and
    # its shape (url + required attribution fields) is Unsplash's, not
    # ours. See recipes/services/unsplash_service.py for the exact keys.
    image = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class SavedRecipe(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recipes",
    )
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name="recipes",
    )

    class Meta:
        unique_together = ("user", "recipe")

    def __str__(self):
        return f"{self.user.email} saved {self.recipe.title}"