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
    class Meta:
        model = User
        fields = ["id", "email", "created_at"]
        read_only_fields = ["id", "email", "created_at"]