from django.urls import path

from .views import ProductListAPIView, health_check

app_name = "fridge"

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("products/", ProductListAPIView.as_view(), name="product-list"),
]
