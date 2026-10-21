from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "modules.tenants"
    label = "tenants"
    verbose_name = "Tenancy, membership & RBAC"
