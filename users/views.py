from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from users.serializers import (
    LoginSerializer,
    RegisterSerializer,
    UserRegistrationResponseSerializer,
)


@extend_schema(
    tags=["Authentication"],
    request=RegisterSerializer,
    responses={201: UserRegistrationResponseSerializer},
    description="Register a new user using email and password.",
)
class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        response_serializer = UserRegistrationResponseSerializer(user)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Authentication"],
    request=LoginSerializer,
    responses={
        200: {
            "type": "object",
            "properties": {
                "refresh": {"type": "string"},
                "access": {"type": "string"},
            },
        }
    },
    description="Authenticate user with email and password and return JWT tokens.",
)
class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer


@extend_schema(
    tags=["Authentication"],
    responses={
        200: {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "user": {"type": "string"},
            },
        }
    },
    description="Protected test endpoint. Requires valid JWT access token.",
)
class ProtectedTestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "message": "JWT works",
                "user": request.user.email,
            },
            status=status.HTTP_200_OK,
        )