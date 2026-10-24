from django.contrib import admin

from modules.departures.models import Departure, DepartureEvent


@admin.register(Departure)
class DepartureAdmin(admin.ModelAdmin):
    list_display = (
        "code", "package", "start_at", "seat_capacity", "seats_taken",
        "seats_blocked", "status", "environment", "created_at",
    )
    list_filter = ("environment", "status")
    search_fields = ("code", "city_of_origin")
    readonly_fields = ("seats_taken", "created_at", "updated_at")


@admin.register(DepartureEvent)
class DepartureEventAdmin(admin.ModelAdmin):
    list_display = ("departure", "prior_status", "next_status", "actor", "created_at")
    list_filter = ("environment", "next_status")
    readonly_fields = ("departure", "environment", "prior_status", "next_status", "actor", "reason", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
