from django.contrib import admin

from modules.trial.models import DemoBooking, TenantTrial, TenantTrialEvent, TrialEntitlement


@admin.register(TenantTrial)
class TenantTrialAdmin(admin.ModelAdmin):
    list_display = ("tenant", "status", "started_at", "ends_at", "converted_at", "dummy_count")
    list_filter = ("status",)
    search_fields = ("tenant__slug",)
    readonly_fields = ("started_at", "converted_at", "config_snapshot_json", "created_at", "updated_at")


@admin.register(TrialEntitlement)
class TrialEntitlementAdmin(admin.ModelAdmin):
    list_display = ("tenant", "dummy_booking_limit", "internal_users_limit")
    search_fields = ("tenant__slug",)


@admin.register(TenantTrialEvent)
class TenantTrialEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "tenant", "type", "actor")
    list_filter = ("type",)
    search_fields = ("tenant__slug",)
    readonly_fields = ("tenant", "actor", "type", "reason", "metadata_json", "occurred_at")

    def has_change_permission(self, request, obj=None):
        return False  # append-only (Spec §5.1)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DemoBooking)
class DemoBookingAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "tenant", "created_at")
    search_fields = ("code", "label", "tenant__slug")
