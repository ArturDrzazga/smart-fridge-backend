from django.urls import path

from recipes.views import RecipeSuggestionTaskStatusView, RecipeSuggestionView

app_name = "recipes"

urlpatterns = [
    path("suggestions/", RecipeSuggestionView.as_view(), name="recipe-suggestions"),
    path(
        "suggestions/<str:task_id>/",
        RecipeSuggestionTaskStatusView.as_view(),
        name="recipe-suggestion-status",
    ),
]