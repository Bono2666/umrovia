from django.apps import AppConfig


class TrialConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "modules.trial"
    label = "trial"
    verbose_name = "Trial lifecycle, kuota & demo data"
