from drf_spectacular.utils import OpenApiResponse, extend_schema, OpenApiExample
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from users.serializers import (
    ChangePasswordSerializer,
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
            response=dict,
            description="Successfully authenticated. "
                        "Returns access and refresh JWT tokens.",
            examples=[
                OpenApiExample(
                    name="JWTTokenPairExample",
                    value={
                        "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    },
                )
            ],
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
            response=dict,
            description="Token verified successfully.",
            examples=[
                OpenApiExample(
                    name="ProtectedTestSuccessExample",
                    summary="Success",
                    value={
                        "message": "JWT works",
                        "user": "user@example.com",
                    },
                )
            ],
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
        API view to retrieve or partially update details of the
        currently authenticated user. first_name/last_name are the only
        editable fields via PATCH - email is fixed (it's the login
        identifier) and created_at is server-managed.
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
        description="Returns details (id, email, name, date joined) "
                    "for the currently authenticated user.",
    )
    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Authentication"],
        request=UserProfileSerializer,
        responses={
            200: UserProfileSerializer,
            400: OpenApiResponse(description="Validation error."),
            401: OpenApiResponse(
                description="Authentication credentials "
                            "were not provided or are invalid."
            ),
        },
        examples=[
            OpenApiExample(
                "Request",
                value={"first_name": "John", "last_name": "Doe"},
                request_only=True,
            ),
        ],
        description="Partially update the currently authenticated "
                    "user's first_name and/or last_name.",
    )
    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Authentication"],
    request=ChangePasswordSerializer,
    responses={
        200: OpenApiResponse(description="Password changed successfully."),
        400: OpenApiResponse(
            description="Validation error (e.g. current password is incorrect, "
                        "new password too short)."
        ),
        401: OpenApiResponse(
            description="Authentication credentials "
                        "were not provided or are invalid."
        ),
    },
    examples=[
        OpenApiExample(
            "Request",
            value={
                "current_password": "OldPassword123!",
                "new_password": "NewPassword456!",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Success",
            value={"detail": "Password changed successfully."},
            response_only=True,
            status_codes=["200"],
        ),
        OpenApiExample(
            "Wrong current password",
            value={"current_password": ["Current password is incorrect."]},
            response_only=True,
            status_codes=["400"],
        ),
    ],
    description="Change the currently authenticated user's password. "
                "Requires the current password to authorize the change.",
)
class ChangePasswordView(APIView):
    """
        API view allowing the currently authenticated user to change
        their own password, given their current password.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])

        return Response(
            {"detail": "Password changed successfully."},
            status=status.HTTP_200_OK,
        )