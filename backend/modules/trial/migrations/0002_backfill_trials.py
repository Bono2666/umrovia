"""Backfill trial untuk tenant lama (pra-S04) yang sudah terprovisioning.

Tenant dengan state PROVISIONING/TRIAL yang memiliki membership ACTIVE tetapi
belum punya trial record: buat entitlement + trial (started_at = membership
Owner paling awal, ends_at = +30 hari, §7.1/TR01), environment demo, event
STARTED, lalu transisikan state → TRIAL. Idempoten; aman dijalankan ulang.
"""
import uuid
from datetime import timedelta

from django.db import migrations

TRIAL_DAYS = 30
DUMMY_BOOKING_LIMIT = 20
INTERNAL_USERS_LIMIT = 3


def backfill_trials(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    TenantMembership = apps.get_model("tenants", "TenantMembership")
    TenantEnvironment = apps.get_model("tenants", "TenantEnvironment")
    TenantTrial = apps.get_model("trial", "TenantTrial")
    TrialEntitlement = apps.get_model("trial", "TrialEntitlement")
    TenantTrialEvent = apps.get_model("trial", "TenantTrialEvent")

    for tenant in Tenant.objects.filter(state__in=["PROVISIONING", "TRIAL"]):
        if TenantTrial.objects.filter(tenant=tenant).exists():
            continue
        membership = (
            TenantMembership.objects.filter(tenant=tenant, status="ACTIVE").order_by("created_at").first()
        )
        if membership is None:  # belum terprovisioning penuh — biarkan (trial mulai saat provisioning)
            continue
        started_at = membership.created_at
        snapshot = {
            "dummy_booking_limit": DUMMY_BOOKING_LIMIT,
            "internal_users_limit": INTERNAL_USERS_LIMIT,
            "trial_features_json": {},
            "trial_days": TRIAL_DAYS,
        }
        TrialEntitlement.objects.get_or_create(
            tenant=tenant,
            defaults={
                "dummy_booking_limit": DUMMY_BOOKING_LIMIT,
                "internal_users_limit": INTERNAL_USERS_LIMIT,
            },
        )
        TenantTrial.objects.create(
            tenant=tenant,
            started_at=started_at,
            ends_at=started_at + timedelta(days=TRIAL_DAYS),
            status="RUNNING",
            config_snapshot_json=snapshot,
        )
        TenantEnvironment.objects.get_or_create(
            tenant=tenant, environment="demo", defaults={"state": "ACTIVE"}
        )
        TenantTrialEvent.objects.create(
            id=uuid.uuid4(), tenant=tenant, type="STARTED", metadata_json={"backfill": True}
        )
        tenant.state = "TRIAL"
        tenant.save(update_fields=["state", "updated_at"])


def noop(apps, schema_editor):
    """Backfill data tidak dibatalkan (trial record tidak dihapus otomatis)."""


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0002_tenantenvironment"),
        ("trial", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_trials, noop),
    ]
