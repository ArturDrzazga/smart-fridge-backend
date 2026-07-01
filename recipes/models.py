from django.db import models

from config import settings


class Recipe(models.Model):
    title = models.CharField(max_length=255)
    ingredients = models.JSONField(default=list)
    steps = models.TextField()
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
