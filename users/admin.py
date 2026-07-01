from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from users.models import User


@admin.register(User)
class UserAdmin(UserAdmin):
    list_display = ("email", "is_staff", "is_active", "created_at")
    list_filter = ("is_staff", "is_superuser", "is_active")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Permissions", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions"
                )
            }
        ),
        ("Important dates", {"fields": ("last_login", "created_at")}),
    )

    readonly_fields = ("created_at", "last_login")

    search_fields = ("email",)
    ordering = ("email",)
