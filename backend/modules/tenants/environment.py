"""Resolusi environment + guard write untuk tabel bisnis S07+ (Spec §2.2).

Aturan environment (§2.2, §7.2):
- Selama trial: satu-satunya environment ACTIVE = demo → semua write masuk
  demo (produk fisik mustahil).
- Setelah konversi: demo → READ_ONLY, production → ACTIVE → write masuk
  production; data demo tetap terbaca (read-only view) namun TIDAK bisa
  ditulis lagi.
- Client tidak pernah memilih environment — selalu resolve server-side dari
  state tenant (anti client-trust, §18.4).

Rumah bersama di domain `tenants` (model `TenantEnvironment` milik sini);
dipakai oleh modul pilgrims (S07) dan catalog/departures (S08).
"""
from rest_framework.exceptions import PermissionDenied

from modules.tenants.models import Environment, EnvironmentState, Tenant, TenantEnvironment


class EnvironmentReadOnlyError(PermissionDenied):
    """Ditulis ke environment yang sedang read-only (mis. demo pasca-konversi)."""


def resolve_active_environment(tenant: Tenant) -> str:
    """Environment aktif untuk write: production bila sudah ACTIVE, selain itu demo."""
    active = TenantEnvironment.objects.filter(tenant=tenant, state=EnvironmentState.ACTIVE)
    if active.filter(environment=Environment.PRODUCTION).exists():
        return Environment.PRODUCTION
    return Environment.DEMO


def assert_environment_writable(tenant: Tenant, environment: str) -> None:
    """Tolak write ke environment non-ACTIVE (demo → READ_ONLY setelah konversi)."""
    row = TenantEnvironment.objects.filter(tenant=tenant, environment=environment).first()
    if row is None or row.state != EnvironmentState.ACTIVE:
        raise EnvironmentReadOnlyError(
            f"Environment '{environment}' sedang tidak menerima perubahan (read-only)."
        )
