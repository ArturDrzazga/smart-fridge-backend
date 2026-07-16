from rest_framework import serializers


class RecipeSuggestionRequestSerializer(serializers.Serializer):
    """
    ingredients is optional. If omitted (or an empty list), the backend
    automatically fetches the current user's fridge/freezer contents from
    the database instead, prioritizing items closest to their expiry date.
    """
    ingredients = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )

