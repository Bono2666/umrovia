"""Scoped query policy (defense-in-depth layer di atas RLS, Spec §2.2).

Semua model bisnis tenant-scoped ber-`tenant_id` harus memakai TenantScopedModel.
Manager MENOLAK semua query tanpa context tenant (fail-closed) — bukan mengembalikan
data kosong. RLS PostgreSQL diaktifkan di F02 (docs/adr/0001-tenant-isolation.md).

`without_tenant_guard()` hanya untuk jalur sah yang memang butuh akses lintas-context:
provisioning signup (belum ada tenant context), resolusi membership di middleware,
job background dengan konteks bertanda tangan, dan support elevated (wajib audit).
"""
from django.db import models

from modules.tenants.context import get_current_tenant


class TenantContextMissingError(RuntimeError):
    """Dilempar saat query tenant-scoped dijalankan tanpa context tenant."""


class TenantScopedQuerySet(models.QuerySet):
    def for_current_tenant(self):
        tenant = get_current_tenant()
        if tenant is None:
            raise TenantContextMissingError("Query tenant-scoped tanpa context tenant ditolak (fail-closed).")
        return self.filter(tenant=tenant)


class TenantScopedManager(models.Manager.from_queryset(TenantScopedQuerySet)):
    def get_queryset(self):
        # Setiap query otomatis ter-scope ke context tenant (fail-closed).
        return super().get_queryset().for_current_tenant()

    def for_current_tenant(self):
        return self.get_queryset()

    def without_tenant_guard(self):
        """Bypass scope — hanya untuk jalur sah (lihat docstring modul)."""
        return super().get_queryset()


class TenantScopedModel(models.Model):
    """Base untuk semua tabel bisnis tenant-scoped (kolom tenant_id wajib, Spec §5)."""

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="%(class)ss")

    objects = TenantScopedManager()

    class Meta:
        abstract = True
