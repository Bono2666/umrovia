"""Backfill S05: role sistem/default + TenantSettings untuk tenant lama.

- Role `Owner` per tenant ditandai `is_system=True` (dilindungi: nama/permission
  tak bisa diubah, tak bisa dihapus).
- Membuat role default (matriks §3, salinan beku `DEFAULT_ROLE_PERMISSIONS`)
  bila belum ada.
- Membuat baris `TenantSettings` 1:1 bila belum ada.
Idempoten; aman dijalankan ulang.
"""
from django.db import migrations

DEFAULT_ROLES = {
    "Admin": [
        "memberships.read",
        "memberships.write",
        "tenant.settings.read",
        "tenant.settings.write",
        "roles.read",
        "roles.write",
        "bookings.create",
        "bookings.read",
        "departures.manage",
        "documents.approve",
        "reports.read",
        "trial.read",
        "trial.demo_booking.create",
    ],
    "Sales": [
        "bookings.create",
        "bookings.read",
        "invoices.read",
        "leads.manage",
        "trial.demo_booking.create",
    ],
    "Finance": [
        "payments.verify",
        "wallet.topup",
        "invoices.read",
        "reports.read",
        "bank_accounts.read",
        "bank_accounts.write",
    ],
    "Operations": ["departures.manage", "documents.approve", "manifest.read", "bookings.read"],
    "Document Reviewer": ["documents.review", "bookings.read"],
}


def backfill_roles_and_settings(apps, schema_editor):
    Role = apps.get_model("tenants", "Role")
    Tenant = apps.get_model("tenants", "Tenant")
    TenantSettings = apps.get_model("tenants", "TenantSettings")

    for tenant in Tenant.objects.all():
        Role.objects.update_or_create(
            tenant=tenant,
            name="Owner",
            defaults={"permissions_json": ["*"], "is_system": True},
        )
        for role_name, grants in DEFAULT_ROLES.items():
            Role.objects.get_or_create(
                tenant=tenant, name=role_name, defaults={"permissions_json": grants, "is_system": False}
            )
        TenantSettings.objects.get_or_create(tenant=tenant)


def noop(apps, schema_editor):
    """Backfill data tidak dibatalkan."""


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0003_tenantsettings"),
    ]

    operations = [
        migrations.RunPython(backfill_roles_and_settings, noop),
    ]
