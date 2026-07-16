from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from users.views import LoginView, ProtectedTestView, RegisterView, UserProfileView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("protected-test/", ProtectedTestView.as_view(), name="protected_test"),
    path("me/", UserProfileView.as_view(), name="user-profile"),
]