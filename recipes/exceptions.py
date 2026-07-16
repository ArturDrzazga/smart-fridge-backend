import logging

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("django")

class GeminiTimeoutError(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Ai service temporarily unavailable"
    default_code = "ai_service_unavailable"

def custom_exception_handler(exc, context):
    view_name = context.get("view").__class__.__name__ \
        if context.get("view") else "UnknownView"
    logger.error(f"Exception caught in {view_name}: {str(exc)}", exc_info=True)

    exc_class_name = exc.__class__.__name__

    if exc_class_name == "GeminiTimeoutError" or "timeout" in str(exc).lower():
        return Response(
            {"error": "AI service temporarily unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    response = exception_handler(exc, context)

    if response is None:
        return Response(
            {"error": "An unexpected error occurred. Please try again later."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    if response is not None and "detail" in response.data:
        response.data = {"error": response.data["detail"]}

    return response