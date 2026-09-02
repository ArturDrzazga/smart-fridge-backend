import logging
from datetime import timedelta

from celery.exceptions import TimeoutError as CeleryTimeoutError
from celery.result import AsyncResult
from django.utils import timezone
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
from recipes.services.task_registry import get_task_owner, register_task
from recipes.services.unsplash_service import get_recipe_image
from recipes.tasks import generate_recipe_suggestions_task, generate_recipe_task

logger = logging.getLogger("django")

STEPS_SEPARATOR = "\n"


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
        tags=["Recipes"],
        request=RecipeSuggestionRequestSerializer,
        responses={
            202: OpenApiResponse(
                response=RecipeSuggestionQueuedResponseSerializer,
                description="Recipe suggestion task queued successfully.",
            ),
            429: OpenApiResponse(
                description="Daily request limit reached for this user/IP.",
            ),
            503: OpenApiResponse(
                description="Failed to queue the task (Gemini/Celery unavailable).",
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
            OpenApiExample(
                "Queued response",
                value={
                    "task_id": "bd56719b-9b55-4754-8b22-42b460314d84",
                    "status": "PENDING",
                    "message": "Recipe suggestion task queued successfully.",
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = RecipeSuggestionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = (
            request.user.id
            if request.user.is_authenticated
            else f"anon_{request.META.get('REMOTE_ADDR')}"
        )

        is_allowed, remaining = check_daily_limit(user_id)
        if not is_allowed:
            return Response(
                {"error": "Daily limit reached", "remaining": 0},
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

        # Record who submitted this task, so the status endpoint can
        # tell "never existed" apart from "still pending" (Celery can't
        # do this on its own), and can refuse to show this task's
        # result to a different user.
        register_task(task.id, user_id)

        return Response(
            {
                "task_id": task.id,
                "status": task.status,
                "message": "Recipe suggestion task queued successfully.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class RecipeSuggestionTaskStatusView(APIView):
    """
    GET /api/recipes/suggestions/<task_id>/

    Only returns a task's status/result to the same user who submitted
    it (tracked via recipes.services.task_registry). A task_id that was
    never issued, has expired from the registry, or belongs to a
    different user all return an identical 404 - this endpoint never
    reveals which of those is the case.

    When the task status is SUCCESS, the generated recipes are automatically
    persisted to the database on-the-fly and assigned a numeric ID, making
    them immediately ready for saving via POST /api/recipes/save/.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Recipes"],
        responses={
            200: OpenApiResponse(
                response=RecipeSuggestionTaskStatusResponseSerializer,
                description="Recipe suggestion task status fetched successfully.",
            ),
            404: OpenApiResponse(
                description="Task not found (or belongs to another user).",
            ),
        },
        examples=[
            OpenApiExample(
                "Task still processing",
                value={
                    "task_id": "bd56719b-9b55-4754-8b22-42b460314d84",
                    "status": "PENDING",
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Task completed successfully",
                value={
                    "task_id": "bd56719b-9b55-4754-8b22-42b460314d84",
                    "status": "SUCCESS",
                    "result": {
                        "recipes": [
                            {
                                "id": 42,
                                "title": "Classic Fluffy Scrambled Eggs",
                                "description": "A quick, comforting breakfast ready in minutes.",
                                "servings": 2,
                                "ingredients": [
                                    "eggs",
                                    "butter",
                                    "salt",
                                    "black pepper",
                                ],
                                "steps": [
                                    "Crack the eggs into a bowl and whisk until combined.",
                                    "Melt butter in a non-stick skillet over medium-low heat.",
                                ],
                                "prep_time_minutes": 10,
                            }
                        ]
                    },
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request, task_id):
        owner = get_task_owner(task_id)
        if owner is None or owner != str(request.user.id):
            return Response(
                {"detail": "Task not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        task_result = AsyncResult(task_id)

        response_data = {
            "task_id": task_id,
            "status": task_result.status,
        }

        if task_result.status == "SUCCESS":
            mapped = _map_to_generate_schema(task_result.result)
            response_data["result"] = _persist_generated_recipes(mapped)
        elif task_result.status == "FAILURE":
            response_data["error"] = str(task_result.result)

        return Response(response_data, status=status.HTTP_200_OK)


def _map_to_generate_schema(gemini_result):
    """
    Maps the internal Gemini result shape to the schema required by the API,
    supporting both standard ('ingredients', 'steps') and alternative keys.
    """
    recipes = []
    for recipe in gemini_result.get("recipes", []):
        ingredients = recipe.get("ingredients")
        if ingredients is None:
            ingredients_used = recipe.get("ingredients_used", [])
            missing_ingredients = recipe.get("missing_ingredients", [])
            ingredients = [*ingredients_used, *missing_ingredients]

        steps = recipe.get("steps") or recipe.get("instructions", [])

        recipes.append(
            {
                "title": recipe.get("title", ""),
                "description": recipe.get("description"),
                "servings": recipe.get("servings"),
                "ingredients": ingredients,
                "steps": steps,
                "prep_time_minutes": recipe.get("prep_time_minutes"),
                "difficulty": recipe.get("difficulty"),
            }
        )
    return {"recipes": recipes}


def _persist_generated_recipes(mapped_result):
    """
    Saves each generated recipe as a Recipe row in the database, and
    adds the resulting id to each recipe dict in-place. Also cleans up
    unassigned orphaned recipes older than 24 hours to prevent table bloat.

    This is what makes POST /api/recipes/save/ usable right after
    POST /api/recipes/generate/: without persisting here, generated
    recipes had no id at all, so there was no legitimate recipe_id a
    client could ever pass to /save/ (reported by Oleksandr).
    """

    threshold = timezone.now() - timedelta(hours=24)
    Recipe.objects.filter(recipes__isnull=True, created_at__lt=threshold).delete()

    for recipe in mapped_result["recipes"]:
        image = get_recipe_image(recipe["title"])
        recipe_obj = Recipe.objects.create(
            title=recipe["title"],
            description=recipe.get("description"),
            servings=recipe.get("servings"),
            ingredients=recipe["ingredients"],
            steps=STEPS_SEPARATOR.join(recipe["steps"]),
            prep_time_minutes=recipe.get("prep_time_minutes"),
            difficulty=recipe.get("difficulty"),
            image=image,
        )
        recipe["id"] = recipe_obj.id
        recipe["difficulty"] = recipe_obj.difficulty
        recipe["image"] = image
    return mapped_result


class RecipeGenerateView(APIView):
    """
    Core AI recipe generation endpoint (SFA-426).

    Automatically fetches the current user's fridge contents (SFA-427),
    compiles the confirmed Gemini prompt template, and dispatches the
    request via a Celery async task (SFA-428). Unlike
    POST /api/recipes/suggestions/, this endpoint waits (up to 60s) for
    the task result and responds synchronously with status 200, so
    frontend clients don't need to poll a separate status endpoint.

    Each generated recipe is also persisted as a Recipe row, and its id
    is included in the response, so it can immediately be passed to
    POST /api/recipes/save/ to bookmark it.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Recipes"],
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
        examples=[
            OpenApiExample(
                "Example response",
                value={
                    "recipes": [
                        {
                            "id": 42,
                            "title": "Classic Fluffy Scrambled Eggs",
                            "description": "A quick, comforting breakfast ready in minutes.",
                            "servings": 2,
                            "ingredients": ["eggs", "butter", "salt", "black pepper"],
                            "steps": [
                                "Crack the eggs into a bowl and whisk until combined.",
                                "Melt butter in a non-stick skillet over medium-low heat.",
                                "Pour in the eggs and gently stir until softly set.",
                                "Season with salt and pepper, and serve immediately.",
                            ],
                            "prep_time_minutes": 10,
                        }
                    ]
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "Daily limit reached",
                value={
                    "detail": "Daily request limit reached (5 per day). Please try again tomorrow."
                },
                response_only=True,
                status_codes=["429"],
            ),
            OpenApiExample(
                "Gemini unavailable",
                value={
                    "detail": "Recipe generation service is currently unavailable. Please try again later."
                },
                response_only=True,
                status_codes=["503"],
            ),
        ],
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
            result = task.get(timeout=120)
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

        mapped = _map_to_generate_schema(result)
        mapped = _persist_generated_recipes(mapped)

        return Response(mapped, status=status.HTTP_200_OK)


# --- Saved recipes ---------------------------------------------------


def _serialize_saved_recipe(recipe):
    """Converts a Recipe model instance into the API's list-based shape."""
    steps_text = recipe.steps or ""
    steps = [line for line in steps_text.split(STEPS_SEPARATOR) if line]
    return {
        "id": recipe.id,
        "title": recipe.title,
        "description": recipe.description,
        "servings": recipe.servings,
        "ingredients": recipe.ingredients or [],
        "steps": steps,
        "prep_time_minutes": recipe.prep_time_minutes,
        "difficulty": recipe.difficulty,
        "image": recipe.image,
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
        tags=["Recipes"],
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
        examples=[
            OpenApiExample(
                "Request",
                value={"recipe_id": 1},
                request_only=True,
            ),
            OpenApiExample(
                "Saved successfully",
                value={"id": 5, "user_id": 2, "recipe_id": 1},
                response_only=True,
                status_codes=["201"],
            ),
            OpenApiExample(
                "Already saved",
                value={"detail": "This recipe is already saved to your favourites."},
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Recipe not found",
                value={"detail": "Recipe not found."},
                response_only=True,
                status_codes=["404"],
            ),
        ],
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
        tags=["Recipes"],
        responses={
            200: OpenApiResponse(
                response=SavedRecipeResponseSerializer(many=True),
                description="List of the authenticated user's saved recipes.",
            ),
        },
        examples=[
            OpenApiExample(
                "Example response",
                value=[
                    {
                        "id": 1,
                        "title": "Cheesy Tomato Omelette",
                        "description": "A rich, cheesy twist on a classic omelette.",
                        "servings": 2,
                        "ingredients": ["eggs", "tomatoes", "cheese"],
                        "steps": [
                            "Whisk eggs with a pinch of salt and pepper.",
                            "Pour into a hot, buttered pan.",
                        ],
                        "prep_time_minutes": 15,
                        "created_at": "2026-07-16T18:31:27.995668Z",
                    }
                ],
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "No saved recipes",
                value=[],
                response_only=True,
                status_codes=["200"],
            ),
        ],
    )
    def get(self, request):
        saved_recipes = (
            SavedRecipe.objects.filter(user=request.user)
            .select_related("recipe")
            .order_by("-recipe__created_at")
        )
        data = [_serialize_saved_recipe(saved.recipe) for saved in saved_recipes]
        return Response(data, status=status.HTTP_200_OK)


class SavedRecipeDetailView(APIView):
    """
    DELETE /api/recipes/saved/<id>/ (SFA-367)

    Allows an authenticated user to unsave/remove a recipe from their
    favourites. <id> refers to the SavedRecipe row's id (not the
    underlying Recipe's id).

    Object-level permission (SFA-368): the queryset is filtered by both
    id AND the requesting user, so a SavedRecipe belonging to another
    user is indistinguishable from one that doesn't exist at all - both
    correctly return 404, without leaking whether the id exists for
    someone else.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Recipes"],
        responses={
            204: OpenApiResponse(description="Recipe removed from favourites."),
            404: OpenApiResponse(
                description="Saved recipe not found (or belongs to another user).",
            ),
        },
        examples=[
            OpenApiExample(
                "Not found",
                value={"detail": "Saved recipe not found."},
                response_only=True,
                status_codes=["404"],
            ),
        ],
    )
    def delete(self, request, id):
        try:
            saved = SavedRecipe.objects.get(id=id, user=request.user)
        except SavedRecipe.DoesNotExist:
            return Response(
                {"detail": "Saved recipe not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        saved.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecipeDetailView(APIView):
    """
    GET /api/recipes/<id>/

    Returns full details for a single recipe by its Recipe id (not a
    SavedRecipe id). Used by the Recipe Details screen on the frontend.

    Any authenticated user can view any recipe by id: recipes generated
    via /generate/ or /suggestions/ aren't owned by a specific user
    until saved, so there's no ownership check here - ownership only
    applies to the saved bookmark itself (see SavedRecipeDetailView).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Recipes"],
        responses={
            200: OpenApiResponse(
                response=SavedRecipeResponseSerializer,
                description="Recipe details fetched successfully.",
            ),
            404: OpenApiResponse(description="Recipe not found."),
        },
        examples=[
            OpenApiExample(
                "Not found",
                value={"detail": "Recipe not found."},
                response_only=True,
                status_codes=["404"],
            ),
        ],
    )
    def get(self, request, id):
        try:
            recipe = Recipe.objects.get(id=id)
        except Recipe.DoesNotExist:
            return Response(
                {"detail": "Recipe not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(_serialize_saved_recipe(recipe), status=status.HTTP_200_OK)