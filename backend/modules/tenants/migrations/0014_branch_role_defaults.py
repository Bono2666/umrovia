"""Cabang (MOD-03): grant baru hanya untuk role default yang belum diubah."""
from django.db import migrations

BASELINES = {
    "Admin": ['memberships.read', 'memberships.write', 'tenant.settings.read', 'tenant.settings.write', 'roles.read', 'roles.write', 'bookings.create', 'bookings.read', 'packages.read', 'packages.write', 'departures.read', 'departures.write', 'departures.manage', 'documents.approve', 'documents.requirements.manage', 'manifest.read', 'manifest.publish', 'manifest.export', 'pilgrims.read', 'pilgrims.write', 'reports.read', 'trial.read', 'trial.demo_booking.create', 'invoices.read', 'invoices.issue', 'payments.create', 'payments.read', 'payments.read_all', 'receipts.read', 'notifications.read', 'notifications.manage', 'leads.manage', 'bookings.discount', 'agents.read', 'agents.manage', 'commissions.read'],
    "Sales": ['bookings.create', 'bookings.read', 'invoices.read', 'leads.manage', 'packages.read', 'departures.read', 'pilgrims.read', 'pilgrims.write', 'trial.demo_booking.create', 'payments.create', 'payments.read', 'receipts.read', 'agents.read'],
    "Finance": ['payments.verify', 'wallet.topup', 'invoices.read', 'reports.read', 'bank_accounts.read', 'bank_accounts.write', 'packages.read', 'departures.read', 'pilgrims.read', 'invoices.issue', 'payments.create', 'payments.read', 'payments.read_all', 'receipts.read', 'payments.reverse', 'wallet.read', 'wallet.export', 'notifications.read', 'reports.finance', 'expenses.read', 'expenses.write', 'agents.read', 'commissions.read', 'commissions.policies', 'commissions.approve', 'commissions.pay'],
    "Operations": ['packages.read', 'packages.write', 'departures.read', 'departures.write', 'departures.manage', 'documents.approve', 'documents.requirements.manage', 'manifest.read', 'manifest.publish', 'manifest.export', 'bookings.read', 'pilgrims.read', 'notifications.read', 'reports.read'],
}
ADDED = {
    "Admin": ['branches.read', 'branches.manage'],
    "Sales": ['branches.read'],
    "Finance": ['branches.read'],
    "Operations": ['branches.read'],
}


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
    dependencies = [("tenants", "0013_branch")]
    operations = [migrations.RunPython(upgrade, migrations.RunPython.noop)]
