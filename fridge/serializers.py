from rest_framework import serializers

from fridge.models import Product


class ProductSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source="get_category_display",
        read_only=True
    )
    storage_display = serializers.CharField(
        source="get_storage_display",
        read_only=True
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "category",
            "category_display",
            "storage",
            "storage_display",
            "quantity",
            "expiry_date",
            "created_at"
        ]

        extra_kwargs = {
            "name": {"required": True, "allow_blank": False, "max_length": 100},
            "quantity": {"required": False, "max_length": 20},
            "expiry_date": {"required": True},
        }
