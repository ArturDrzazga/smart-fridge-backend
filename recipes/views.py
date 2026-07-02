from celery.result import AsyncResult
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from recipes.serializers import RecipeSuggestionRequestSerializer
from recipes.tasks import generate_recipe_suggestions_task


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
                "Recipe suggestion request",
                value={"ingredients": ["eggs", "tomatoes", "cheese"]},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        serializer = RecipeSuggestionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ingredients = serializer.validated_data["ingredients"]
        task = generate_recipe_suggestions_task.delay(ingredients)

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