from django.apps import AppConfig


class PlatformConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "modules.platform"
    label = "platform"
    verbose_name = "Platform control plane"

    def ready(self):
        from . import checks  # noqa: F401
