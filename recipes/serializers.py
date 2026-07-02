from rest_framework import serializers


class RecipeSuggestionRequestSerializer(serializers.Serializer):
    ingredients = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
    )