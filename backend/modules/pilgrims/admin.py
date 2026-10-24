from django.contrib import admin

from modules.pilgrims.models import Pilgrim, PilgrimDocument


@admin.register(Pilgrim)
class PilgrimAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "environment", "status", "identity_masked", "passport_masked", "created_at")
    list_filter = ("environment", "status")
    search_fields = ("code", "name")
    readonly_fields = ("identity_encrypted", "identity_hash", "passport_encrypted", "created_at", "updated_at")


@admin.register(PilgrimDocument)
class PilgrimDocumentAdmin(admin.ModelAdmin):
    list_display = ("pilgrim", "kind", "version", "status", "created_at")
    list_filter = ("environment", "kind", "status")
    search_fields = ("object_key",)
