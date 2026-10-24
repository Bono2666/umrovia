from django.apps import AppConfig


class ManifestConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "modules.manifest"
    label = "manifest"
    verbose_name = "Checklist & manifest"
