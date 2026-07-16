import logging

from celery.exceptions import TimeoutError as CeleryTimeoutError
from celery.result import AsyncResult
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from recipes.exceptions import GeminiTimeoutError
from recipes.models import Recipe, SavedRecipe
from recipes.serializers import (
    RecipeGenerateResponseSerializer,
    RecipeSaveRequestSerializer,
    RecipeSuggestionRequestSerializer,
    SavedRecipeCreateResponseSerializer,
    SavedRecipeResponseSerializer,
)
from recipes.services.limits import check_daily_limit
from recipes.services.rate_limit import (
    DAILY_RECIPE_GENERATION_LIMIT,
    check_and_increment_daily_limit,
)
from recipes.tasks import generate_recipe_suggestions_task, generate_recipe_task

logger = logging.getLogger("django")


class RecipeSuggestionQueuedResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    status = serializers.CharField()
    message = serializers.CharField()


class RecipeSuggestionTaskStatusResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    status = serializers.CharField()
    result = serializers.JSONField(required=False)
    error = serializers.CharField(required=False)


class RecipeSuggestionView(APIView):
    @extend_schema(
        request=RecipeSuggestionRequestSerializer,
        responses={
            202: OpenApiResponse(
                response=RecipeSuggestionQueuedResponseSerializer,
                description="Recipe suggestion task queued successfully.",
            ),
        },
        examples=[
            OpenApiExample(
                "Auto-fetch from fridge (recommended)",
                value={},
                request_only=True,
            ),
            OpenApiExample(
                "Manual ingredient override",
                value={"ingredients": ["eggs", "tomatoes", "cheese"]},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = RecipeSuggestionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = request.user.id \
            if request.user.is_authenticated \
            else f"anon_{request.META.get('REMOTE_ADDR')}"

        is_allowed, remaining = check_daily_limit(user_id)
        if not is_allowed:
            return Response(
                {
                    "error": "Daily limit reached",
                    "remaining": 0
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        ingredients = serializer.validated_data.get("ingredients") or None
        # If the client didn't provide an explicit ingredient list, pass
        # None so the Celery task knows to fetch the user's fridge
        # contents from the database instead.
        try:
            task = generate_recipe_task.delay(user_id=user_id, ingredients=ingredients)
        except Exception as exc:
            logger.error(f"Failed to queue Celery task: {str(exc)}")
            raise GeminiTimeoutError()

        return Response(
            {
                "task_id": task.id,
                "status": task.status,
                "message": "Recipe suggestion task queued successfully.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class RecipeSuggestionTaskStatusView(APIView):
    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=RecipeSuggestionTaskStatusResponseSerializer,
                description="Recipe suggestion task status fetched successfully.",
            ),
        }
    )
    def get(self, request, task_id):
        task_result = AsyncResult(task_id)

        response_data = {
            "task_id": task_id,
            "status": task_result.status,
        }

        if task_result.status == "SUCCESS":
            response_data["result"] = task_result.result
        elif task_result.status == "FAILURE":
            response_data["error"] = str(task_result.result)

        return Response(response_data, status=status.HTTP_200_OK)


def _map_to_generate_schema(gemini_result):
    """
    Maps the internal Gemini result shape
    (title, ingredients_used, missing_ingredients, instructions, prep_time_minutes)
    to the simplified schema required by POST /api/recipes/generate/:
    (title, ingredients, steps).
    """
    recipes = []
    for recipe in gemini_result.get("recipes", []):
        ingredients_used = recipe.get("ingredients_used", [])
        missing_ingredients = recipe.get("missing_ingredients", [])
        recipes.append(
            {
                "title": recipe.get("title", ""),
                "ingredients": [*ingredients_used, *missing_ingredients],
                "steps": recipe.get("instructions", []),
            }
        )
    return {"recipes": recipes}


class RecipeGenerateView(APIView):
    """
    Core AI recipe generation endpoint (SFA-426).

    Automatically fetches the current user's fridge contents (SFA-427),
    compiles the confirmed Gemini prompt template, and dispatches the
    request via a Celery async task (SFA-428). Unlike
    POST /api/recipes/suggestions/, this endpoint waits (up to 60s) for
    the task result and responds synchronously with status 200, so
    frontend clients don't need to poll a separate status endpoint.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(
                response=RecipeGenerateResponseSerializer,
                description="Recipes generated successfully.",
            ),
            429: OpenApiResponse(
                description=(
                    f"Daily request limit reached "
                    f"({DAILY_RECIPE_GENERATION_LIMIT} per day)."
                ),
            ),
            503: OpenApiResponse(
                description="Gemini API is currently unavailable or timed out.",
            ),
        },
    )
    def post(self, request):
        allowed = check_and_increment_daily_limit(request.user.id)
        if not allowed:
            return Response(
                {
                    "detail": (
                        f"Daily request limit reached "
                        f"({DAILY_RECIPE_GENERATION_LIMIT} per day). "
                        f"Please try again tomorrow."
                    )
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        task = generate_recipe_suggestions_task.delay(request.user.id, None)

        try:
            result = task.get(timeout=60)
        except CeleryTimeoutError:
            return Response(
                {"detail": "Recipe generation timed out. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            return Response(
                {
                    "detail": (
                        "Recipe generation service is currently unavailable. "
                        "Please try again later."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(_map_to_generate_schema(result), status=status.HTTP_200_OK)


# --- Saved recipes ---------------------------------------------------

STEPS_SEPARATOR = "\n"


def _serialize_saved_recipe(recipe):
    """Converts a Recipe model instance into the API's list-based shape."""
    steps_text = recipe.steps or ""
    steps = [line for line in steps_text.split(STEPS_SEPARATOR) if line]
    return {
        "id": recipe.id,
        "title": recipe.title,
        "ingredients": recipe.ingredients or [],
        "steps": steps,
        "created_at": recipe.created_at,
    }


class SaveRecipeView(APIView):
    """
    Allows an authenticated user to save an existing recipe (by id) to
    their favourites (SFA-357). Prevents duplicate bookmarks via an
    explicit check backed by the SavedRecipe.unique_together
    ("user", "recipe") constraint (SFA-358).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=RecipeSaveRequestSerializer,
        responses={
            201: OpenApiResponse(
                response=SavedRecipeCreateResponseSerializer,
                description="Recipe saved to favourites successfully.",
            ),
            400: OpenApiResponse(
                description="This recipe is already saved to favourites.",
            ),
            404: OpenApiResponse(description="Recipe not found."),
        },
    )
    def post(self, request):
        serializer = RecipeSaveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recipe_id = serializer.validated_data["recipe_id"]

        try:
            recipe = Recipe.objects.get(id=recipe_id)
        except Recipe.DoesNotExist:
            return Response(
                {"detail": "Recipe not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        already_saved = SavedRecipe.objects.filter(
            user=request.user, recipe=recipe
        ).exists()
        if already_saved:
            return Response(
                {"detail": "This recipe is already saved to your favourites."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        saved = SavedRecipe.objects.create(user=request.user, recipe=recipe)

        return Response(
            {
                "id": saved.id,
                "user_id": request.user.id,
                "recipe_id": recipe.id,
            },
            status=status.HTTP_201_CREATED,
        )


class SavedRecipeListView(APIView):
    """
    Returns all recipes saved by the authenticated user (SFA-362), with
    full recipe details (title, ingredients, steps). Uses
    select_related("recipe") (SFA-363) to avoid N+1 queries.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=SavedRecipeResponseSerializer(many=True),
                description="List of the authenticated user's saved recipes.",
            ),
        },
    )
    def get(self, request):
        saved_recipes = (
            SavedRecipe.objects.filter(user=request.user)
            .select_related("recipe")
            .order_by("-recipe__created_at")
        )
        data = [
            _serialize_saved_recipe(saved.recipe) for saved in saved_recipes
        ]
        return Response(data, status=status.HTTP_200_OK)