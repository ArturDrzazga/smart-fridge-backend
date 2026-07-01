from django.urls import path

from .views import health_check

app_name = "fridge"

urlpatterns = [
    path("health/", health_check, name="health-check"),
]
