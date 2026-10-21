from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from modules.identity.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "status", "is_email_verified", "is_staff", "created_at")
    search_fields = ("email", "full_name")
    list_filter = ("status", "is_staff", "is_active")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("full_name",)}),
        ("Status", {"fields": ("status", "email_verified_at", "mfa_enabled", "is_active")}),
        ("Permissions", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Tanggal", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "full_name", "password1", "password2", "is_staff")}),
    )
    readonly_fields = ("created_at", "updated_at", "last_login")
    filter_horizontal = ("groups", "user_permissions")
