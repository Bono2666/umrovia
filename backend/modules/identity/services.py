"""Service identity: token sekali-pakai (verifikasi email & reset password) + email.

Mengikuti Spec §7.1 (link verify TTL + one-time nonce) dan §19.4 T07 (test token
invalid/kedaluwarsa). Hanya SHA-256 token yang disimpan di DB.
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from modules.identity.models import AuthToken, User, UserStatus

EMAIL_VERIFY_TTL = timedelta(hours=24)
PASSWORD_RESET_TTL = timedelta(minutes=60)


class AuthTokenError(Exception):
    """Token tidak valid / kedaluwarsa / sudah dipakai."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(
    user: User, kind: str, ttl: timedelta, *, invalidate_previous: bool = True, ip: str | None = None
) -> str:
    """Buat token baru; kembalikan token mentah (hanya dikirim via email)."""
    now = timezone.now()
    if invalidate_previous:
        AuthToken.objects.filter(user=user, kind=kind, used_at__isnull=True).update(used_at=now)
    raw = secrets.token_urlsafe(32)
    AuthToken.objects.create(
        user=user,
        kind=kind,
        token_sha256=_sha256(raw),
        expires_at=now + ttl,
        created_ip=ip,
    )
    return raw


def consume_token(raw: str, kind: str) -> User:
    """Validasi & tandai token terpakai (atomik). Melempar AuthTokenError bila gagal."""
    if not raw:
        raise AuthTokenError("token_missing", "Token tidak ditemukan.")
    with transaction.atomic():
        token = (
            AuthToken.objects.select_for_update()
            .filter(token_sha256=_sha256(raw), kind=kind)
            .first()
        )
        if token is None:
            raise AuthTokenError("invalid_token", "Token tidak valid.")
        if token.used_at is not None:
            raise AuthTokenError("token_used", "Token sudah pernah dipakai.")
        if token.expires_at <= timezone.now():
            raise AuthTokenError("token_expired", "Token kedaluwarsa. Minta link baru.")
        token.used_at = timezone.now()
        token.save(update_fields=["used_at", "updated_at"])
        return token.user


def send_verification_email(user: User, raw_token: str) -> str:
    """Kirim email verifikasi; mengembalikan link (untuk log/dev)."""
    url = f"{settings.TENANT_APP_URL.rstrip('/')}/verify-email?token={raw_token}"
    send_mail(
        subject="Umrovia — verifikasi email Anda",
        message=(
            f"Halo,\n\nAktifkan akun Umrovia Anda dengan membuka link ini:\n{url}\n\n"
            f"Berlaku 24 jam dan hanya bisa dipakai sekali. Jika Anda tidak mendaftar, "
            f"abaikan email ini.\n\n— {settings.BRAND_NAME}"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
    return url


def send_password_reset_email(user: User, raw_token: str) -> str:
    url = f"{settings.TENANT_APP_URL.rstrip('/')}/reset-password?token={raw_token}"
    send_mail(
        subject="Umrovia — reset password",
        message=(
            f"Halo,\n\nAtur ulang password akun Umrovia Anda:\n{url}\n\n"
            f"Berlaku 60 menit dan hanya bisa dipakai sekali. Jika Anda tidak meminta "
            f"ini, abaikan email ini.\n\n— {settings.BRAND_NAME}"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
    return url


def mark_verified(user: User) -> User:
    """Tandai email terverifikasi (idempoten)."""
    if user.email_verified_at is None:
        user.email_verified_at = timezone.now()
    if user.status == UserStatus.PENDING_VERIFICATION:
        user.status = UserStatus.ACTIVE
    user.save(update_fields=["email_verified_at", "status", "updated_at"])
    return user


def membership_summary(user: User) -> list[dict]:
    """Daftar membership milik user (dipakai /me & response login)."""
    from modules.tenants.models import TenantMembership

    rows = (
        TenantMembership.objects.without_tenant_guard()
        .filter(user=user)
        .select_related("tenant", "role")
        .order_by("created_at")
    )
    return [
        {
            "tenant": {
                "id": str(m.tenant_id),
                "slug": m.tenant.slug,
                "display_name": m.tenant.display_name,
                "state": m.tenant.state,
            },
            "role": m.role.name if m.role else None,
            "status": m.status,
        }
        for m in rows
    ]


def user_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "email_verified": user.is_email_verified,
        "memberships": membership_summary(user),
    }
