"""CRM (MOD-19): Admin mendapat `leads.manage` bila role default belum diubah (Sales sudah sejak awal)."""
from django.db import migrations

BASELINE = ["memberships.read", "memberships.write", "tenant.settings.read", "tenant.settings.write", "roles.read", "roles.write", "bookings.create", "bookings.read", "packages.read", "packages.write", "departures.read", "departures.write", "departures.manage", "documents.approve", "documents.requirements.manage", "manifest.read", "manifest.publish", "manifest.export", "pilgrims.read", "pilgrims.write", "reports.read", "trial.read", "trial.demo_booking.create", "invoices.read", "invoices.issue", "payments.create", "payments.read", "payments.read_all", "receipts.read", "notifications.read", "notifications.manage"]


def upgrade(apps, schema_editor):
    Role = apps.get_model("tenants", "Role")
    for role in Role.objects.using(schema_editor.connection.alias).filter(name="Admin", is_system=False, tenant__isnull=False):
        raw = role.permissions_json
        current = [key for key, allowed in raw.items() if allowed] if isinstance(raw, dict) else raw
        if isinstance(current, list) and all(isinstance(value, str) for value in current) and set(current) == set(BASELINE):
            role.permissions_json = list(dict.fromkeys(BASELINE + ["leads.manage"]))
            role.save(update_fields=["permissions_json"])


class Migration(migrations.Migration):
    dependencies = [("tenants", "0010_tenant_lifecycle")]
    operations = [migrations.RunPython(upgrade, migrations.RunPython.noop)]
