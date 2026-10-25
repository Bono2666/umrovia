"""S11 grants for untouched S10 defaults; custom roles remain unchanged."""
from django.db import migrations

BASELINE = {
    "Admin": [
        "memberships.read",
        "memberships.write",
        "tenant.settings.read",
        "tenant.settings.write",
        "roles.read",
        "roles.write",
        "bookings.create",
        "bookings.read",
        "packages.read",
        "packages.write",
        "departures.read",
        "departures.write",
        "departures.manage",
        "documents.approve",
        "documents.requirements.manage",
        "manifest.read",
        "manifest.publish",
        "manifest.export",
        "pilgrims.read",
        "pilgrims.write",
        "reports.read",
        "trial.read",
        "trial.demo_booking.create"
    ],
    "Finance": [
        "payments.verify",
        "wallet.topup",
        "invoices.read",
        "reports.read",
        "bank_accounts.read",
        "bank_accounts.write",
        "packages.read",
        "departures.read",
        "pilgrims.read"
    ],
    "Sales": [
        "bookings.create",
        "bookings.read",
        "invoices.read",
        "leads.manage",
        "packages.read",
        "departures.read",
        "pilgrims.read",
        "pilgrims.write",
        "trial.demo_booking.create"
    ]
}
ADDITIONS = {
    "Admin": [
        "invoices.read",
        "invoices.issue",
        "payments.create",
        "payments.read",
        "payments.read_all",
        "receipts.read"
    ],
    "Finance": [
        "invoices.read",
        "invoices.issue",
        "payments.create",
        "payments.read",
        "payments.read_all",
        "receipts.read",
        "payments.reverse"
    ],
    "Sales": [
        "payments.create",
        "payments.read",
        "receipts.read"
    ]
}


def upgrade_payment_roles(apps, schema_editor):
    Role = apps.get_model("tenants", "Role")
    for name, grants in BASELINE.items():
        for role in Role.objects.using(schema_editor.connection.alias).filter(name=name, is_system=False):
            raw = role.permissions_json
            current = [key for key, allowed in raw.items() if allowed] if isinstance(raw, dict) else raw
            if isinstance(current, list) and all(isinstance(value, str) for value in current) and set(current) == set(grants):
                role.permissions_json = list(dict.fromkeys(grants + ADDITIONS[name]))
                role.save(update_fields=["permissions_json"])


class Migration(migrations.Migration):
    dependencies = [("tenants", "0005_operational_role_defaults"), ("payments", "0001_initial")]
    operations = [migrations.RunPython(upgrade_payment_roles, migrations.RunPython.noop)]
