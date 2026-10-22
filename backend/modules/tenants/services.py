"""Provisioning workspace travel (Spec §7.1 langkah 3).

Tenant dibuat saat register (state PENDING_EMAIL — memvalidasi & mengunci slug).
Setelah email terverifikasi, `provision_workspace` membuat:
1. role Owner + membership aktif (dengan guard kuota internal user — TR04),
2. environment demo (ACTIVE; produksi baru ada setelah konversi, §7.2),
3. trial record + entitlement (started_at = provisioning, ends_at = +30 hari),
lalu memutasi state PROVISIONING → TRIAL (§6.1).

Semua idempoten — retry aman (satu tenant, satu trial, §6.1/§7.1).
"""
from django.db import transaction

from modules.tenants.models import (
    Environment,
    EnvironmentState,
    MembershipStatus,
    Role,
    Tenant,
    TenantEnvironment,
    TenantMembership,
    TenantState,
)


class ProvisioningError(Exception):
    pass


@transaction.atomic
def provision_workspace(owner, slug: str) -> Tenant:
    """Provisioning penuh untuk tenant `slug`. Idempoten (retry aman)."""
    # Impor di dalam fungsi: menghindari circular import (trial.services → tenants.models)
    from modules.trial.services import assert_internal_user_quota, start_trial

    tenant = Tenant.objects.select_for_update().filter(slug=slug).first()
    if tenant is None:
        raise ProvisioningError(f"Tenant '{slug}' belum dibuat saat registrasi.")
    if tenant.created_by_id != owner.id:
        raise ProvisioningError("Tenant bukan milik user ini.")

    existing = TenantMembership.objects.without_tenant_guard().filter(tenant=tenant, user=owner).first()
    if existing is None:  # jalur provisioning pertama
        if tenant.state == TenantState.PENDING_EMAIL:
            tenant.state = TenantState.PROVISIONING
            tenant.save(update_fields=["state", "updated_at"])
        role = Role.objects.get_or_create(
            tenant=tenant,
            name="Owner",
            defaults={"permissions_json": ["*"], "is_system": False},  # wildcard (Spec §3 Owner)
        )[0]
        assert_internal_user_quota(tenant)
        TenantMembership.objects.without_tenant_guard().create(
            tenant=tenant,
            user=owner,
            role=role,
            status=MembershipStatus.ACTIVE,
        )
        # Environment demo — produksi hanya muncul saat konversi trial (§7.2)
        TenantEnvironment.objects.get_or_create(
            tenant=tenant, environment=Environment.DEMO, defaults={"state": EnvironmentState.ACTIVE}
        )

    # Trial idempoten; transisikan state PENDING_EMAIL/PROVISIONING → TRIAL (§6.1)
    start_trial(tenant)
    return tenant
