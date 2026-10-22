"""Provisioning workspace travel (Spec §7.1 langkah 3).

Tenant dibuat saat register (state PENDING_EMAIL — memvalidasi & mengunci slug).
Setelah email terverifikasi, `provision_workspace` membuat:
1. role sistem (Owner `is_system` wildcard + Admin/Sales/Finance/Ops/DocReviewer
   sesuai matriks §3) + membership Owner (guard kuota internal user — TR04),
2. environment demo (ACTIVE; produksi baru ada setelah konversi, §7.2),
3. `TenantSettings` 1:1 (§5.1) + trial record (started_at = provisioning,
   ends_at = +30 hari), lalu state PROVISIONING → TRIAL (§6.1).

Semua idempoten — retry aman (satu tenant, satu trial, §6.1/§7.1).
"""
from django.db import transaction
from rest_framework.exceptions import ValidationError

from modules.tenants.models import (
    Environment,
    EnvironmentState,
    MembershipStatus,
    Role,
    Tenant,
    TenantEnvironment,
    TenantMembership,
    TenantSettings,
    TenantState,
)
from modules.tenants.rbac import DEFAULT_ROLE_PERMISSIONS


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
        # Role sistem (matriks §3): Owner is_system+wildcard, lainnya default
        role = Role.objects.get_or_create(
            tenant=tenant,
            name="Owner",
            defaults={"permissions_json": ["*"], "is_system": True},
        )[0]
        for role_name, grants in DEFAULT_ROLE_PERMISSIONS.items():
            if role_name == "Owner":
                continue
            Role.objects.get_or_create(
                tenant=tenant, name=role_name, defaults={"permissions_json": grants, "is_system": False}
            )
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

    # Settings 1:1 tenant (§5.1)
    TenantSettings.objects.get_or_create(tenant=tenant)
    # Trial idempoten; transisikan state PENDING_EMAIL/PROVISIONING → TRIAL (§6.1)
    start_trial(tenant)
    return tenant


# ---------------------------------------------------------------------------
# Staff & role (Spec §8.1 — invite/role/revoke; guard Owner terakhir)
# ---------------------------------------------------------------------------


def _active_owner_count(tenant, exclude_pk=None) -> int:
    qs = TenantMembership.objects.without_tenant_guard().filter(
        tenant=tenant, status=MembershipStatus.ACTIVE, role__name="Owner"
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.count()


def _require_tenant_role(tenant, role) -> None:
    """Role harus milik tenant ini (guard IDOR lintas-tenant)."""
    if role is None or role.tenant_id != tenant.id:

        raise ValidationError({"role_id": "Role tidak ditemukan di workspace ini."})


def invite_member(*, tenant, email: str, role) -> tuple[TenantMembership, bool]:
    """Undang staf (§8.1 POST /memberships).

    - User baru: dibuat `PENDING_VERIFICATION` + membership `INVITED` —
      aktif otomatis saat email-nya diverifikasi (hook VerifyEmailView).
    - User ACTIVE sudah ada: membership langsung `ACTIVE`.
    - Guard kuota internal user trial (TR04) berlaku sebelum create.
    Mengembalikan (membership, user_baru_dibuat).
    """

    from modules.identity.models import User, UserStatus
    from modules.trial.services import assert_internal_user_quota

    _require_tenant_role(tenant, role)
    assert_internal_user_quota(tenant)

    email = email.strip().lower()
    exists = TenantMembership.objects.without_tenant_guard().filter(
        tenant=tenant, user__email__iexact=email
    ).exists()
    if exists:
        raise ValidationError({"email": "Email sudah menjadi anggota workspace ini."})

    user = User.objects.filter(email__iexact=email).first()
    created_user = user is None
    if created_user:
        user = User.objects.create_user(email=email, password=None)  # tanpa password
    member_status = (
        MembershipStatus.ACTIVE if user.status == UserStatus.ACTIVE else MembershipStatus.INVITED
    )
    membership = TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant, user=user, role=role, status=member_status
    )
    return membership, created_user


def assign_membership_role(*, tenant, membership, role) -> str:
    """Ganti role anggota (§8.1 PATCH). Guard: tidak bisa menurunkan Owner
    terakhir. Mengembalikan nama role lama."""

    _require_tenant_role(tenant, role)
    if membership.role_id == role.id:
        return role.name
    old_name = membership.role.name if membership.role else None
    if old_name == "Owner" and role.name != "Owner" and _active_owner_count(tenant, exclude_pk=membership.pk) == 0:
        raise ValidationError({"role_id": "Owner terakhir tidak bisa diturunkan role-nya."})
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    return old_name


def revoke_membership(*, tenant, membership) -> bool:
    """Cabut keanggotaan (soft — status REVOKED, §8.1 DELETE). Idempoten.
    Guard: Owner terakhir tidak bisa dicabut. True bila ada perubahan."""

    if membership.status == MembershipStatus.REVOKED:
        return False
    if membership.role.name == "Owner" and _active_owner_count(tenant, exclude_pk=membership.pk) == 0:
        raise ValidationError({"membership": "Owner terakhir tidak bisa dicabut dari workspace."})
    membership.status = MembershipStatus.REVOKED
    membership.save(update_fields=["status", "updated_at"])
    return True
