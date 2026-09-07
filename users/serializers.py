from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from users.models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "email", "password", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_email(self, value):
        return value.lower().strip()

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserRegistrationResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "created_at"]


class LoginSerializer(TokenObtainPairSerializer):
    username_field = User.EMAIL_FIELD

    def validate(self, attrs):
        if "email" in attrs and isinstance(attrs["email"], str):
            attrs["email"] = attrs["email"].lower().strip()

        try:
            data = super().validate(attrs)
        except AuthenticationFailed:
            raise AuthenticationFailed("Invalid email or password.")

        return data


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Used by both GET /api/auth/me/ (full read) and PATCH /api/auth/me/
    (partial update). first_name/last_name are optional - registration
    only collects email/password, so a user's name starts blank and can
    be set/edited here later (the Profile Modal design shows a name but
    there's currently no registration step that collects one).
    """

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "created_at"]
        read_only_fields = ["id", "email", "created_at"]


class ChangePasswordSerializer(serializers.Serializer):
    """
    Used by POST /api/auth/change-password/. Requires the current
    password to authorize the change, distinct from a password-reset
    flow (which would instead verify identity via emailed token).
    """

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value