from django.contrib import admin

from modules.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "action", "tenant", "actor", "object_type", "ip")
    list_filter = ("action",)
    search_fields = ("object_id", "action")
    readonly_fields = [f.name for f in AuditEvent._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False  # append-only (Spec §5.5)

    def has_delete_permission(self, request, obj=None):
        return False
