from django.contrib import admin

from modules.tenants.models import Role, Tenant, TenantMembership


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("display_name", "slug", "state", "timezone", "created_at")
    list_filter = ("state",)
    search_fields = ("display_name", "legal_name", "slug")
    readonly_fields = ("created_at", "updated_at", "created_by")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "is_system")
    search_fields = ("name",)


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "status")
    list_filter = ("status",)
    search_fields = ("user__email", "tenant__slug")
