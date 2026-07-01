from django.db import models

class Recipe(models.Model):
    title = models.CharField(max_length=255)
    ingredients = models.JSONField(default=list)
    steps = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


