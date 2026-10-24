"""Admin Django — checklist & versi manifest (read-only untuk manifest)."""
from django.contrib import admin

from modules.manifest.models import DocumentRequirement, ManifestVersion


@admin.register(DocumentRequirement)
class DocumentRequirementAdmin(admin.ModelAdmin):
    list_display = ("environment", "package", "kind", "mandatory", "deadline_rule")
    list_filter = ("environment", "mandatory", "deadline_rule")
    search_fields = ("kind", "package__code")
    raw_id_fields = ("package",)


@admin.register(ManifestVersion)
class ManifestVersionAdmin(admin.ModelAdmin):
    list_display = ("departure", "version_no", "published_by", "checksum", "created_at")
    list_filter = ("environment",)
    search_fields = ("departure__code", "checksum")
    raw_id_fields = ("departure", "published_by")
    readonly_fields = (
        "departure",
        "version_no",
        "published_by",
        "snapshot_object_key",
        "checksum",
        "created_at",
    )  # append-only (OPS-04): revisi = versi baru, bukan edit baris

    def has_add_permission(self, request):
        return False
