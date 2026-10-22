"""RBAC — pola permission `domain.object.action` (Spec §3).

Permission = string bertingkat (mis. `payments.verify`, `wallet.topup`,
`departures.publish`, `documents.review`, `reports.export_pii`, `trial.convert`).
Role menyimpan daftar grant di `Role.permissions_json`; Owner memakai wildcard `*`.

Matcher mendukung: `*` (semua), `domain.*` (satu domain), `domain.object.*`
(satu objek), dan exact match. Format dict lama `{"payments.verify": true}`
masih diterima (dipetakan ke grant list).

Matriks default mengikuti Spec §3 (Y = diberi; S/— = TIDAK diberi di v1,
karena mekanisme approval/scope belum ada).
"""
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from modules.tenants.exceptions import TenantContextRequired

# Grant default per role tenant (dipakai saat role dibuat — S05+ & test).
# Catatan: Admin TIDAK mendapat payments.verify / wallet.topup / trial.convert
# / reports.export_pii (matriks §3 = S/—); hanya Owner (wildcard) yang dapat.
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "Owner": ["*"],
    "Admin": [
        "memberships.read",
        "memberships.write",
        "tenant.settings.write",
        "bookings.create",
        "bookings.read",
        "departures.manage",
        "documents.approve",
        "reports.read",
    ],
    "Sales": ["bookings.create", "bookings.read", "invoices.read", "leads.manage"],
    "Finance": ["payments.verify", "wallet.topup", "invoices.read", "reports.read"],
    "Operations": ["departures.manage", "documents.approve", "manifest.read", "bookings.read"],
    "Document Reviewer": ["documents.review", "bookings.read"],
}


def permission_list(role) -> list[str]:
    """Daftar grant permission sebuah role (normalisasi dict lama → list)."""
    raw = getattr(role, "permissions_json", None) if role is not None else None
    if not raw:
        return []
    if isinstance(raw, dict):
        return [key for key, allowed in raw.items() if allowed]
    return list(raw)


def has_permission(grants, permission: str) -> bool:
    """True bila `permission` tercakup grant (wildcard/prefix/exact)."""
    if isinstance(grants, dict):
        grants = [key for key, allowed in grants.items() if allowed]
    for pattern in grants or []:
        if pattern == "*" or pattern == permission:
            return True
        if pattern.endswith(".*") and permission.startswith(pattern[:-1]):
            # `bookings.*` mencakup `bookings.create` DAN `bookings.*.x` prefix umum
            return True
    return False


class TenantPermission(BasePermission):
    """DRF permission: konteks tenant valid + grant role cocok (gagal → 403).

    Tanpa context tenant → lempar TENANT_CONTEXT_REQUIRED (fail-closed);
    context ada tetapi role tidak punya grant → PermissionDenied (403).
    """

    permission: str = ""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        membership = getattr(request, "membership", None)
        if membership is None:
            raise TenantContextRequired()
        if not has_permission(permission_list(membership.role), self.permission):
            raise PermissionDenied(f"Permission '{self.permission}' tidak dimiliki role Anda.")
        return True


def require_permission(permission: str) -> type[TenantPermission]:
    """Factory kelas permission untuk `permission_classes=[..., require_permission("...")]`."""
    class_name = "Has_" + permission.replace(".", "_").replace("*", "all")
    return type(class_name, (TenantPermission,), {"permission": permission, "__doc__": f"Grant wajib: {permission}"})
