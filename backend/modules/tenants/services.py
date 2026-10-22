"""Provisioning workspace travel (Spec §7.1 langkah 3).

Tenant dibuat saat register (state PENDING_EMAIL — memvalidasi & mengunci slug).
Setelah email terverifikasi, `provision_workspace` membuat role Owner + membership
aktif. Trial record & transisi ke TRIAL dikerjakan di S04/F03.
"""
from django.db import transaction

from modules.tenants.models import MembershipStatus, Role, Tenant, TenantMembership


class ProvisioningError(Exception):
    pass


@transaction.atomic
def provision_workspace(owner, slug: str) -> Tenant:
    """Buat Owner role + membership untuk tenant `slug`. Idempoten (retry aman)."""
    tenant = Tenant.objects.select_for_update().filter(slug=slug).first()
    if tenant is None:
        raise ProvisioningError(f"Tenant '{slug}' belum dibuat saat registrasi.")
    if tenant.created_by_id != owner.id:
        raise ProvisioningError("Tenant bukan milik user ini.")

    existing = TenantMembership.objects.without_tenant_guard().filter(tenant=tenant, user=owner).first()
    if existing is not None:  # provisioning retry / verify ulang
        return tenant

    role = Role.objects.get_or_create(
        tenant=tenant,
        name="Owner",
        defaults={"permissions_json": {"*": "*"}, "is_system": False},
    )[0]
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant,
        user=owner,
        role=role,
        status=MembershipStatus.ACTIVE,
    )
    return tenant
