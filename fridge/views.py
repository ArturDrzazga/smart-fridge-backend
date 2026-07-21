from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import filters, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from fridge.models import Product
from fridge.serializers import ProductSerializer


@extend_schema(
    description="Simple endpoint to verify the "
                "operational status of the fridge module.",
    responses={
        200: OpenApiResponse(
            description="Service is healthy and running.",
            examples=[
                {
                    "summary": "Success",
                    "value": {"status": "OK", "message": "Hello World"}
                }
            ]
        )
    }
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
        Returns operational status of the fridge module.
    """
    return Response({"status": "OK", "message": "Hello World"})

@extend_schema_view(
    list=extend_schema(
        description="Retrieves a list of products "
                    "belonging to the authenticated user. "
                    "Supports filtering by category and storage type, "
                    "as well as ordering.",
        responses={
            200: ProductSerializer(many=True),
            401: OpenApiResponse(
                description="Authentication credentials "
                            "were not provided or are invalid."
            ),
        }
    ),
    create=extend_schema(
        description="Adds a new product to the fridge/freezer "
                    "for the authenticated user.",
        responses={
            201: ProductSerializer,
            400: OpenApiResponse(
                description="Invalid request payload / validation error."
            ),
            401: OpenApiResponse(
                description="Authentication credentials "
                            "were not provided or are invalid."
            ),
        }
    ),
    retrieve=extend_schema(
        description="Retrieves detailed information about "
                    "a specific product owned by the user.",
        responses={
            200: ProductSerializer,
            401: OpenApiResponse(
                description="Authentication credentials "
                            "were not provided or are invalid."
            ),
            404: OpenApiResponse(
                description="Product not found or does "
                            "not belong to the authenticated user."
            ),
        }
    ),
    update=extend_schema(
        description="Replaces all fields of an existing "
                    "product owned by the user.",
        responses={
            200: ProductSerializer,
            400: OpenApiResponse(
                description="Invalid request payload / validation error."
            ),
            401: OpenApiResponse(
                description="Authentication credentials "
                            "were not provided or are invalid."
            ),
            404: OpenApiResponse(
                description="Product not found or does "
                            "not belong to the authenticated user."
            ),
        }
    ),
    partial_update=extend_schema(
        description="Updates specific fields of an existing "
                    "product owned by the user.",
        responses={
            200: ProductSerializer,
            400: OpenApiResponse(
                description="Invalid request payload / validation error."
            ),
            401: OpenApiResponse(
                description="Authentication credentials "
                            "were not provided or are invalid."
            ),
            404: OpenApiResponse(
                description="Product not found or does "
                            "not belong to the authenticated user."
            ),
        }
    ),
    destroy=extend_schema(
        description="Removes a specific product "
                    "from the authenticated user's inventory.",
        responses={
            204: OpenApiResponse(description="Product successfully deleted."),
            401: OpenApiResponse(
                description="Authentication credentials "
                            "were not provided or are invalid."
            ),
            404: OpenApiResponse(
                description="Product not found or does "
                            "not belong to the authenticated user."
            ),
        }
    ),
)
class ProductViewSet(viewsets.ModelViewSet):
    """
        API endpoint that allows user products to be viewed,
        created, updated, or deleted.
    """
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["category", "storage"]
    ordering_fields = ["expiry_date", "created_at"]
    ordering = ["expiry_date"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Product.objects.none()
        return Product.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)