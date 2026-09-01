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


class RecipeGenerateItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    ingredients = serializers.ListField(child=serializers.CharField())
    steps = serializers.ListField(child=serializers.CharField())
    prep_time_minutes = serializers.IntegerField(required=False, allow_null=True)


class RecipeGenerateResponseSerializer(serializers.Serializer):
    recipes = RecipeGenerateItemSerializer(many=True)


class RecipeSaveRequestSerializer(serializers.Serializer):
    """
    Saves an existing recipe (by id) to the authenticated user's
    favourites (POST /api/recipes/save/).
    """
    recipe_id = serializers.IntegerField()


class SavedRecipeCreateResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    user_id = serializers.IntegerField()
    recipe_id = serializers.IntegerField()


class SavedRecipeResponseSerializer(serializers.Serializer):
    """
    Full recipe details, used by GET /api/recipes/saved/ and
    GET /api/recipes/<id>/.
    """
    id = serializers.IntegerField()
    title = serializers.CharField()
    ingredients = serializers.ListField(child=serializers.CharField())
    steps = serializers.ListField(child=serializers.CharField())
    prep_time_minutes = serializers.IntegerField(required=False, allow_null=True)
    created_at = serializers.DateTimeField()