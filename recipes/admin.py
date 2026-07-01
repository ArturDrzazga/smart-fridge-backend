from django.contrib import admin

from recipes.models import Recipe, SavedRecipe

admin.site.register(Recipe)
admin.site.register(SavedRecipe)
