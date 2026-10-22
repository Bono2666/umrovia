from django.apps import AppConfig


class TravelFinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "modules.travel_finance"
    label = "travel_finance"
    verbose_name = "Keuangan travel (rekening, kas, expense)"
