from django.urls import path

from recipes.views import (
    RecipeGenerateView,
    RecipeSuggestionTaskStatusView,
    RecipeSuggestionView,
    SavedRecipeListView,
    SaveRecipeView,
)

app_name = "recipes"

urlpatterns = [
    path("suggestions/", RecipeSuggestionView.as_view(), name="recipe-suggestions"),
    path(
        "suggestions/<str:task_id>/",
        RecipeSuggestionTaskStatusView.as_view(),
        name="recipe-suggestion-status",
    ),
    path("generate/", RecipeGenerateView.as_view(), name="recipe-generate"),
    path("save/", SaveRecipeView.as_view(), name="recipe-save"),
    path("saved/", SavedRecipeListView.as_view(), name="recipe-saved-list"),
]