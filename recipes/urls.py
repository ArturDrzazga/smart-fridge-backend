from django.urls import path

from recipes.views import (
    RecipeGenerateView,
    RecipeSuggestionTaskStatusView,
    RecipeSuggestionView,
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
]