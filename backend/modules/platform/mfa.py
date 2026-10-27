"""MFA TOTP staf platform (RFC 6238, SHA-1, 6 digit, langkah 30 detik, toleransi ±1 langkah).

Secret 160-bit dienkripsi (Fernet, kunci PII). Kode yang sudah dipakai tidak
dapat dipakai ulang (langkah terakhir disimpan). Kode pemulihan 10 buah,
sekali pakai, hanya hash SHA-256 yang disimpan dan ditampilkan sekali.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from modules.pilgrims.crypto import decrypt_pii, encrypt_pii
from modules.platform.models import StaffMFA

STEP = 30
DIGITS = 6
WINDOW = 1
RECOVERY_COUNT = 10


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now=None) -> int:
    return int((now if now is not None else time.time()) // STEP)


def code_for(secret: str, now=None) -> str:
    return _code(secret, current_step(now))


def provisioning_uri(secret: str, email: str) -> str:
    issuer = f"{settings.BRAND_NAME} Admin"
    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP}"


def _hash(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").strip().upper().encode()).hexdigest()


def new_recovery_codes() -> tuple[list[str], list[str]]:
    codes = [f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}" for _ in range(RECOVERY_COUNT)]
    return codes, [_hash(code) for code in codes]


def start_enrollment(user) -> tuple[StaffMFA, str]:
    """Secret baru (belum aktif). Perangkat yang sudah terkonfirmasi tidak bisa ditimpa di sini."""
    secret = new_secret()
    device, _ = StaffMFA.objects.update_or_create(user=user, defaults={"secret_encrypted": encrypt_pii(secret), "confirmed_at": None, "last_used_step": 0, "recovery_hashes": []})
    return device, secret


def verify_totp(device: StaffMFA, code: str, now=None) -> bool:
    """Cocokkan kode dalam jendela ±1 langkah; langkah yang sama/lebih lama ditolak (anti-replay)."""
    code = (code or "").replace(" ", "")
    if not (code.isdigit() and len(code) == DIGITS):
        return False
    secret = decrypt_pii(device.secret_encrypted)
    step = current_step(now)
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if candidate > device.last_used_step and hmac.compare_digest(_code(secret, candidate), code):
            device.last_used_step = candidate
            device.save(update_fields=["last_used_step", "updated_at"])
            return True
    return False


def use_recovery_code(device: StaffMFA, code: str) -> bool:
    digest = _hash(code or "")
    if digest not in device.recovery_hashes:
        return False
    device.recovery_hashes = [value for value in device.recovery_hashes if value != digest]
    device.save(update_fields=["recovery_hashes", "updated_at"])
    return True


def confirm(device: StaffMFA, code: str) -> list[str] | None:
    if device.confirmed_at is not None or not verify_totp(device, code):
        return None
    codes, hashes = new_recovery_codes()
    device.confirmed_at = timezone.now()
    device.recovery_hashes = hashes
    device.save(update_fields=["confirmed_at", "recovery_hashes", "updated_at"])
    return codes
