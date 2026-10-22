"""Perekam audit (Spec §5.5 + §13 Audit).

- `changes_json` melewati `redact()`: nilai pada kunci sensitif
  (password/token/account_number/secret/dll) di-mask — nomor rekening penuh
  TIDAK PERNAH masuk audit/log (§5.3 account_masked).
- Kegagalan pencatatan audit TIDAK menjatuhkan operasi utama (logged, lanjut).
"""
import logging
import re

from modules.audit.models import AuditEvent

logger = logging.getLogger(__name__)

_SENSITIVE_KEY_RE = re.compile(r"password|token|secret|account_number|authorization|otp", re.IGNORECASE)
_MASK = "***"


def redact(value, key: str | None = None):
    """Mask nilai sensitif secara rekursif (struktur dict/list dipertahankan)."""
    if key is not None and _SENSITIVE_KEY_RE.search(key):
        return _MASK if value not in (None, "") else value
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def client_ip(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def log_event(
    *,
    action: str,
    request=None,
    actor=None,
    tenant=None,
    object_type: str = "",
    object_id: str = "",
    changes: dict | None = None,
) -> AuditEvent | None:
    """Tulis satu audit event. Bila `tenant`/`actor` tidak diberikan, ambil dari
    context request (`request.tenant`, `request.user`)."""
    if tenant is None:
        tenant = getattr(request, "tenant", None)
    if actor is None:
        user = getattr(request, "user", None)
        actor = user if getattr(user, "is_authenticated", False) else None
    try:
        return AuditEvent.objects.create(
            tenant=tenant,
            actor=actor,
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id else "",
            changes_json=redact(changes or {}),
            ip=client_ip(request),
        )
    except Exception:  # audit tidak boleh menjatuhkan operasi utama
        logger.exception("audit gagal dicatat", extra={"action": action})
        return None
