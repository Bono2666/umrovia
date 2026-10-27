"""Model tenancy (Spec §5.1 — tenants, roles, tenant_memberships).

Tenant = badan usaha travel. State machine (Spec §6.1):
PENDING_EMAIL → PROVISIONING → TRIAL → ACTIVE → (RESTRICTED | SUSPENDED) → TERMINATED

S01 menyediakan skeleton: tabel + constraint + context tenant + scoped manager.
Provisioning signup, RLS PostgreSQL, dan trial modul dikerjakan di F02/F03.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.models import BaseAppModel
from modules.tenants.constants import RESERVED_SLUGS
from modules.tenants.managers import TenantScopedModel


def validate_reserved_slug(slug: str) -> None:
    if slug in RESERVED_SLUGS:
        raise ValidationError(f"Slug '{slug}' terreserve dan tidak boleh dipakai tenant.")


class TenantState(models.TextChoices):
    PENDING_EMAIL = "PENDING_EMAIL", "Menunggu verifikasi email"
    PROVISIONING = "PROVISIONING", "Provisioning"
    TRIAL = "TRIAL", "Trial"
    ACTIVE = "ACTIVE", "Aktif"
    RESTRICTED = "RESTRICTED", "Terbatas (charge pending)"
    SUSPENDED = "SUSPENDED", "Ditangguhkan"
    TERMINATED = "TERMINATED", "Diakhiri"


BLOCKED_STATES = {TenantState.SUSPENDED, TenantState.TERMINATED}


class Tenant(BaseAppModel):
    slug = models.SlugField(max_length=63, unique=True, validators=[validate_reserved_slug])
    legal_name = models.CharField(max_length=160)
    display_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=32, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Jakarta")
    state = models.CharField(max_length=24, choices=TenantState.choices, default=TenantState.PENDING_EMAIL)
    active_at = models.DateTimeField(null=True, blank=True)  # saat berubah ACTIVE
    # S18 lifecycle platform: suspend keamanan menyimpan state sebelumnya agar dapat dipulihkan.
    state_before_suspension = models.CharField(max_length=24, blank=True, default="")
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.CharField(max_length=240, blank=True, default="")
    terminated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "tenant"
        verbose_name_plural = "tenants"
        ordering = ["display_name"]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.slug})"


class Role(BaseAppModel):
    """Role per tenant; tenant NULL = role sistem (contoh: platform admin)."""

    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=64)
    permissions_json = models.JSONField(default=dict, blank=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        verbose_name = "role"
        verbose_name_plural = "roles"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uq_role_tenant_name"),
            models.UniqueConstraint(
                fields=["name"], condition=models.Q(tenant__isnull=True), name="uq_role_system_name"
            ),
        ]

    def __str__(self) -> str:
        scope = self.tenant.slug if self.tenant_id else "system"
        return f"{self.name}@{scope}"


class MembershipStatus(models.TextChoices):
    INVITED = "INVITED", "Diundang"
    ACTIVE = "ACTIVE", "Aktif"
    SUSPENDED = "SUSPENDED", "Ditangguhkan"
    REVOKED = "REVOKED", "Dicabut"


class TenantMembership(TenantScopedModel, BaseAppModel):
    """Keanggotaan user di sebuah travel. branch_id menyusul di F04 (multi-cabang).

    Catatan: provisioning signup membuat membership TANPA context tenant —
    service provisioning memakai `objects.without_tenant_guard()`.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey(Role, null=True, blank=True, on_delete=models.SET_NULL, related_name="memberships")
    status = models.CharField(max_length=16, choices=MembershipStatus.choices, default=MembershipStatus.INVITED)

    class Meta:
        verbose_name = "membership"
        verbose_name_plural = "memberships"
        ordering = ["tenant__display_name", "user__email"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user"], name="uq_membership_tenant_user"),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} @ {self.tenant.slug} ({self.status})"


class Environment(models.TextChoices):
    """Namespace data tenant (Spec §2.2/§5.1): trial = demo; produksi ada
    hanya setelah konversi (§7.2 langkah 2)."""

    DEMO = "demo", "Demo"
    PRODUCTION = "production", "Produksi"


class EnvironmentState(models.TextChoices):
    ACTIVE = "ACTIVE", "Aktif"
    READ_ONLY = "READ_ONLY", "Read-only"
    DISABLED = "DISABLED", "Nonaktif"


class TenantEnvironment(BaseAppModel):
    """Baris environment per tenant (UNIQUE (tenant, environment), §5.1).

    Pada tenant trial: demo ACTIVE, produksi tidak ada (write produksi fisik
    mustahil). Setelah konversi: demo → READ_ONLY, produksi → ACTIVE.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="environments")
    environment = models.CharField(max_length=16, choices=Environment.choices)
    state = models.CharField(max_length=16, choices=EnvironmentState.choices, default=EnvironmentState.ACTIVE)

    class Meta:
        verbose_name = "environment tenant"
        verbose_name_plural = "environment tenants"
        ordering = ["tenant__slug", "environment"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "environment"], name="uq_tenant_environment"),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.slug}:{self.environment} ({self.state})"


class TenantSettings(models.Model):
    """Konfigurasi 1:1 tenant (tenant_id PK, Spec §5.1): branding, invoice, rules."""

    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name="settings", primary_key=True
    )
    branding_json = models.JSONField(default=dict, blank=True)
    invoice_config_json = models.JSONField(default=dict, blank=True)
    rules_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Settings {self.tenant.slug}"
