from django.apps import AppConfig


class BookingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "modules.booking"
    label = "booking"
    verbose_name = "Booking & peserta"
