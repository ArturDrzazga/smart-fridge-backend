import logging

from celery.exceptions import TimeoutError as CeleryTimeoutError
from celery.result import AsyncResult
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from recipes.exceptions import GeminiTimeoutError
from recipes.serializers import RecipeSuggestionRequestSerializer
from recipes.services.limits import check_daily_limit
from recipes.tasks import generate_recipe_task
from recipes.serializers import (
    RecipeGenerateResponseSerializer,
    RecipeSuggestionRequestSerializer,
)
from recipes.services.rate_limit import (
    DAILY_RECIPE_GENERATION_LIMIT,
    check_and_increment_daily_limit,
)
from recipes.tasks import generate_recipe_suggestions_task

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
            else f"anon_{request.META.get("REMOTE_ADDR")}"

        is_allowed, remaining = check_daily_limit(user_id)
        if not is_allowed:
            return Response(
                {
                    "error": "Daily limit reached",
                    "remaining": 0
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        ingredients = request.data.get("ingredients", [])
        try:
            task = generate_recipe_task.delay(user_id=user_id, ingredients=ingredients)
        except Exception as exc:
            logger.error(f"Failed to queue Celery task: {str(exc)}")
            raise GeminiTimeoutError()
        # If the client didn't provide an explicit ingredient list, pass
        # None so the Celery task knows to fetch the user's fridge
        # contents from the database instead.
        ingredients = serializer.validated_data.get("ingredients") or None

        task = generate_recipe_suggestions_task.delay(request.user.id, ingredients)

        return Response(
            {
                "task_id": task.id,
                "status": task.status,
                "message": "Recipe suggestion task queued successfully.",
                "remaining": remaining,
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

    "ingredients" combines both ingredients_used and missing_ingredients,
    since the simplified schema doesn't distinguish between the two.
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

        # ingredients=None -> task automatically fetches the user's
        # fridge contents from the DB (SFA-427), reusing the same
        # fetch-and-prioritize logic as /api/recipes/suggestions/.
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