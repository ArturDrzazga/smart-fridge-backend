from django.urls import path
from django.urls.conf import include
from rest_framework.routers import DefaultRouter

from .views import ProductViewSet, health_check

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")

app_name = "fridge"

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("", include(router.urls)),
]
