"""Otorisasi konsol platform (Spec §3, §18.2): staf aktif + izin Django + MFA segar.

Hostname/frontend bukan otorisasi; setiap endpoint `/platform/*` memeriksa di
server. Role tenant (termasuk Owner `*`) tidak pernah memberi izin platform.
"""
import time

from django.conf import settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

MFA_SESSION_KEY = "platform_mfa_at"
PLATFORM_PERMISSIONS = [
    "platform.console_view", "platform.tenant_manage", "platform.pricing_manage", "platform.audit_view",
    "platform.support_manage", "wallet.settle_topup", "billing.approve_adjustment",
]


class MFARequired(PermissionDenied):
    default_code = "mfa_required"
    default_detail = "Verifikasi MFA diperlukan untuk konsol platform."


def is_platform_staff(user) -> bool:
    return bool(user and user.is_authenticated and user.is_active and user.status == "ACTIVE" and user.email_verified_at and user.is_staff)


def mfa_fresh(request) -> bool:
    verified_at = request.session.get(MFA_SESSION_KEY)
    return isinstance(verified_at, (int, float)) and time.time() - verified_at < settings.PLATFORM_MFA_TTL_SECONDS


def mark_mfa(request) -> None:
    request.session[MFA_SESSION_KEY] = time.time()
    request.session.cycle_key()  # sesi baru setelah step-up (cegah session fixation)


def granted(user) -> list[str]:
    return [perm for perm in PLATFORM_PERMISSIONS if user.has_perm(perm)]


class PlatformStaff(BasePermission):
    """Staf platform tanpa syarat MFA — hanya untuk endpoint pendaftaran/verifikasi MFA."""

    def has_permission(self, request, view):
        if not is_platform_staff(request.user):
            raise PermissionDenied("Hanya staf platform berizin.")
        return True


class PlatformPermission(PlatformStaff):
    permission = "platform.console_view"

    def has_permission(self, request, view):
        super().has_permission(request, view)
        if not mfa_fresh(request):
            raise MFARequired()
        if not request.user.has_perm(self.permission):
            raise PermissionDenied(f"Izin platform '{self.permission}' tidak dimiliki.")
        return True


def require_platform(permission: str) -> type[PlatformPermission]:
    return type(f"Platform_{permission.replace('.', '_')}", (PlatformPermission,), {"permission": permission})
