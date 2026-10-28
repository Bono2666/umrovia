from django.apps import AppConfig


class WalletConfig(AppConfig):
    name = "modules.wallet"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import checks  # noqa: F401
