from django.contrib import admin

from modules.catalog.models import TravelPackage


@admin.register(TravelPackage)
class TravelPackageAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "kind", "price_idr", "status", "published", "environment", "created_at")
    list_filter = ("environment", "kind", "status", "published")
    search_fields = ("code", "name")
    readonly_fields = ("created_at", "updated_at")
