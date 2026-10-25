"""S12: upgrade only the untouched S11 Finance role; preserve custom grants."""
from django.db import migrations

BASELINE = ['payments.verify', 'wallet.topup', 'invoices.read', 'reports.read', 'bank_accounts.read', 'bank_accounts.write', 'packages.read', 'departures.read', 'pilgrims.read', 'invoices.issue', 'payments.create', 'payments.read', 'payments.read_all', 'receipts.read', 'payments.reverse']


def upgrade(apps, schema_editor):
    Role = apps.get_model("tenants", "Role")
    for role in Role.objects.using(schema_editor.connection.alias).filter(name="Finance", is_system=False, tenant__isnull=False):
        raw = role.permissions_json
        current = [key for key, allowed in raw.items() if allowed] if isinstance(raw, dict) else raw
        if isinstance(current, list) and all(isinstance(value, str) for value in current) and set(current) == set(BASELINE):
            role.permissions_json = list(dict.fromkeys(BASELINE + ["wallet.read", "wallet.export"]))
            role.save(update_fields=["permissions_json"])


class Migration(migrations.Migration):
    dependencies = [("tenants", "0006_payment_role_defaults"), ("wallet", "0001_initial")]
    operations = [migrations.RunPython(upgrade, migrations.RunPython.noop)]
