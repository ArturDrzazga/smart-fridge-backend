from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from users.serializers import (
    LoginSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserRegistrationResponseSerializer,
)


@extend_schema(
    tags=["Authentication"],
    request=RegisterSerializer,
    responses={
        201: UserRegistrationResponseSerializer,
        400: OpenApiResponse(
            description="Validation error / email already exists."
        ),
    },
    description="Register a new user using email and password.",
)
class RegisterView(APIView):
    """
        API view for registering new users in the system.
    """
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
        200: OpenApiResponse(
            description="Successfully authenticated. "
                        "Returns access and refresh JWT tokens.",
            examples=[
                {
                    "summary": "JWT Token Pair",
                    "value": {
                        "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                    }
                }
            ]
        ),
        400: OpenApiResponse(
            description="Invalid credentials or bad request format."
        ),
        401: OpenApiResponse(
            description="Authentication failed (e.g. inactive account)."
        )
    },
    description="Authenticate user with email "
                "and password and return JWT access/refresh tokens.",
)
class LoginView(TokenObtainPairView):
    """
        API view for user login. Returns JWT access and refresh tokens.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer


@extend_schema(
    tags=["Authentication"],
    responses={
        200: OpenApiResponse(
            description="Token verified successfully.",
            examples=[
                {
                    "summary": "Success",
                    "value": {
                        "message": "JWT works",
                        "user": "user@example.com"
                    }
                }
            ]
        ),
        401: OpenApiResponse(
            description="Authentication credentials "
                        "were not provided or are invalid."
        ),
    },
    description="Protected test endpoint. "
                "Requires a valid JWT access token in the Authorization header.",
)
class ProtectedTestView(APIView):
    """
        API view to verify JWT token authentication functionality.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "message": "JWT works",
                "user": request.user.email,
            },
            status=status.HTTP_200_OK,
        )


class UserProfileView(APIView):
    """
        API view to retrieve details of the currently authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Authentication"],
        responses={
            200: UserProfileSerializer,
            401: OpenApiResponse(
                description="Authentication credentials "
                            "were not provided or are invalid."
            ),
        },
        description="Returns details (id, email, date joined) "
                    "for the currently authenticated user.",
    )
    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)