from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from fridge.models import Product
from fridge.serializers import ProductSerializer


@api_view(["GET"])
def health_check(request):
    return Response({"status": "OK", "message": "Hello World"})


class ProductListAPIView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Product.objects.filter(user=self.request.user)
