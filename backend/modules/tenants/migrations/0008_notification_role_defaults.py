"""S16: tambahkan grant notifikasi hanya ke role default yang belum diubah; grant kustom dipertahankan."""
from django.db import migrations

BASELINES = {
    "Admin": ["memberships.read", "memberships.write", "tenant.settings.read", "tenant.settings.write", "roles.read", "roles.write", "bookings.create", "bookings.read", "packages.read", "packages.write", "departures.read", "departures.write", "departures.manage", "documents.approve", "documents.requirements.manage", "manifest.read", "manifest.publish", "manifest.export", "pilgrims.read", "pilgrims.write", "reports.read", "trial.read", "trial.demo_booking.create", "invoices.read", "invoices.issue", "payments.create", "payments.read", "payments.read_all", "receipts.read"],
    "Finance": ["payments.verify", "wallet.topup", "invoices.read", "reports.read", "bank_accounts.read", "bank_accounts.write", "packages.read", "departures.read", "pilgrims.read", "invoices.issue", "payments.create", "payments.read", "payments.read_all", "receipts.read", "payments.reverse", "wallet.read", "wallet.export"],
    "Operations": ["packages.read", "packages.write", "departures.read", "departures.write", "departures.manage", "documents.approve", "documents.requirements.manage", "manifest.read", "manifest.publish", "manifest.export", "bookings.read", "pilgrims.read"],
}
ADDED = {"Admin": ["notifications.read", "notifications.manage"], "Finance": ["notifications.read"], "Operations": ["notifications.read"]}


def upgrade(apps, schema_editor):
    Role = apps.get_model("tenants", "Role")
    for name, baseline in BASELINES.items():
        for role in Role.objects.using(schema_editor.connection.alias).filter(name=name, is_system=False, tenant__isnull=False):
            raw = role.permissions_json
            current = [key for key, allowed in raw.items() if allowed] if isinstance(raw, dict) else raw
            if isinstance(current, list) and all(isinstance(value, str) for value in current) and set(current) == set(baseline):
                role.permissions_json = list(dict.fromkeys(baseline + ADDED[name]))
                role.save(update_fields=["permissions_json"])


class Migration(migrations.Migration):
    dependencies = [("tenants", "0007_wallet_role_defaults")]
    operations = [migrations.RunPython(upgrade, migrations.RunPython.noop)]
