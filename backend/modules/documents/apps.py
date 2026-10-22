from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "modules.documents"
    label = "documents"
    verbose_name = "Dokumen (template invoice/kuitansi; checklist menyusul S07)"
