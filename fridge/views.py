from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from fridge.models import Product
from fridge.serializers import ProductSerializer


@api_view(["GET"])
def health_check(request):
    return Response({"status": "OK", "message": "Hello World"})


class ProductListAPIView(generics.ListCreateAPIView):
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