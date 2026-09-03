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
class RecipeImageSerializer(serializers.Serializer):
    """
    Unsplash photo data. Required attribution fields (photographer_name,
    photographer_url, unsplash_url) must be displayed by the frontend
    wherever the image is shown, per Unsplash's API guidelines.
    """
    url = serializers.URLField(allow_null=True)
    unsplash_url = serializers.URLField(allow_null=True)
    download_location = serializers.URLField(allow_null=True)
    photographer_name = serializers.CharField(allow_null=True)
    photographer_url = serializers.URLField(allow_null=True)
class RecipeGenerateItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField(required=False, allow_null=True)
    servings = serializers.IntegerField(required=False, allow_null=True)
    ingredients = serializers.ListField(child=serializers.CharField())
    steps = serializers.ListField(child=serializers.CharField())
    prep_time_minutes = serializers.IntegerField(required=False, allow_null=True)
    difficulty = serializers.ChoiceField(
        choices=["easy", "medium", "hard"], required=False, allow_null=True
    )
    image = RecipeImageSerializer(required=False, allow_null=True)
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

    saved_id is the SavedRecipe row's id (only populated by
    GET /saved/) - this is the id DELETE /saved/<id>/ actually expects,
    not the recipe's own id.
    """
    id = serializers.IntegerField()
    saved_id = serializers.IntegerField(required=False, allow_null=True)
    title = serializers.CharField()
    description = serializers.CharField(required=False, allow_null=True)
    servings = serializers.IntegerField(required=False, allow_null=True)
    ingredients = serializers.ListField(child=serializers.CharField())
    steps = serializers.ListField(child=serializers.CharField())
    prep_time_minutes = serializers.IntegerField(required=False, allow_null=True)
    difficulty = serializers.ChoiceField(
        choices=["easy", "medium", "hard"], required=False, allow_null=True
    )
    image = RecipeImageSerializer(required=False, allow_null=True)
    created_at = serializers.DateTimeField()