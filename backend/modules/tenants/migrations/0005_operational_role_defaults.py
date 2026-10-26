"""Upgrade untouched S05/S07/S08 role defaults to the S10 permission set.

Frozen historical grants; customized roles and Owner remain unchanged.
Rollback preserves grants because their original revision cannot be recovered.
"""
from django.db import migrations

LEGACY_ROLES = {
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
        "trial.demo_booking.create"
    ],
    "Sales": [
        "bookings.create",
        "bookings.read",
        "invoices.read",
        "leads.manage",
        "trial.demo_booking.create"
    ],
    "Finance": [
        "payments.verify",
        "wallet.topup",
        "invoices.read",
        "reports.read",
        "bank_accounts.read",
        "bank_accounts.write"
    ],
    "Operations": [
        "departures.manage",
        "documents.approve",
        "manifest.read",
        "bookings.read"
    ],
    "Document Reviewer": [
        "documents.review",
        "bookings.read"
    ]
}

SPRINT_ADDITIONS = [
    {
        "Admin": [
            "pilgrims.read",
            "pilgrims.write"
        ],
        "Sales": [
            "pilgrims.read",
            "pilgrims.write"
        ],
        "Finance": [
            "pilgrims.read"
        ],
        "Operations": [
            "pilgrims.read"
        ],
        "Document Reviewer": [
            "pilgrims.read"
        ]
    },
    {
        "Admin": [
            "packages.read",
            "packages.write",
            "departures.read",
            "departures.write"
        ],
        "Sales": [
            "packages.read",
            "departures.read"
        ],
        "Finance": [
            "packages.read",
            "departures.read"
        ],
        "Operations": [
            "packages.read",
            "packages.write",
            "departures.read",
            "departures.write"
        ]
    },
    {
        "Admin": [
            "documents.requirements.manage",
            "manifest.read",
            "manifest.publish",
            "manifest.export"
        ],
        "Operations": [
            "documents.requirements.manage",
            "manifest.publish",
            "manifest.export"
        ]
    }
]

def upgrade_operational_roles(apps, schema_editor):
    Role = apps.get_model("tenants", "Role")
    for name, baseline in LEGACY_ROLES.items():
        current = list(baseline)
        known_versions = {frozenset(current)}
        for additions in SPRINT_ADDITIONS:
            current.extend(additions.get(name, []))
            known_versions.add(frozenset(current))
        for role in Role.objects.using(schema_editor.connection.alias).filter(name=name, is_system=False):
            raw = role.permissions_json
            if isinstance(raw, dict):
                grants = [key for key, allowed in raw.items() if allowed]
            elif isinstance(raw, list) and all(isinstance(item, str) for item in raw):
                grants = raw
            else:
                continue
            if frozenset(grants) in known_versions and set(grants) != set(current):
                role.permissions_json = current
                role.save(update_fields=["permissions_json"])


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0004_backfill_roles_settings"),
        ("manifest", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(upgrade_operational_roles, migrations.RunPython.noop),
    ]
