"""Enkripsi & normalisasi field sensitif jamaah (Spec §5.2 identity_encrypted,
§10.1: passport/KTP "store encrypted, log redacted"; §5.2 "search normalisasi
aman; jangan global-unique identity").

- Nilai mentah (NIK, nomor paspor) dienkripsi Fernet → hanya `*_encrypted` di DB;
  API hanya pernah mengirim varian masked (4 digit terakhir, pola §5.3).
- `identity_hash` = HMAC-SHA256 ber-key (turunan PII_ENCRYPTION_KEY + tenant)
  atas nilai ternormalisasi → dipakai pencarian/duplikat TANPA dekripsi dan
  tanpa korelasi lintas-tenant (hash berbeda per tenant).
- Key hilang/berubah → dekripsi gagal jelas (PIIDecryptionError), bukan data
  korup diam-diam.
"""
import hashlib
import hmac
import re
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class PIIDecryptionError(Exception):
    """Dekripsi field sensitif gagal (key salah/hilang atau token rusak)."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.PII_ENCRYPTION_KEY
    if not key:
        raise PIIDecryptionError("PII_ENCRYPTION_KEY belum dikonfigurasi.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise PIIDecryptionError("PII_ENCRYPTION_KEY bukan key Fernet yang valid.") from exc


def encrypt_pii(value: str) -> str:
    """Enkripsi nilai mentah → token Fernet (urlsafe base64, string)."""
    if not value:
        return ""
    return _fernet().encrypt(value.encode()).decode()


def decrypt_pii(token: str) -> str:
    """Dekripsi token → nilai mentah. Hanya untuk jalur sah (bukan API publik)."""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise PIIDecryptionError("Field sensitif tidak dapat didekripsi.") from exc


def normalize_digits(value: str) -> str:
    """Hanya digit — normalisasi NIK untuk hash & pencarian."""
    return re.sub(r"\D", "", value or "")


def normalize_passport(value: str) -> str:
    """Huruf besar + alfanumerik — normalisasi nomor paspor."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def mask_last4(value: str) -> str:
    """Simpan maksimal 4 karakter terakhir — sisanya asterisk (pola §5.3)."""
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 4:
        return "*" * len(cleaned)
    return "*" * (len(cleaned) - 4) + cleaned[-4:]


def identity_hash(tenant_id, normalized_value: str) -> str:
    """HMAC-SHA256 key-tenant-scoped atas nilai ternormalisasi (dedup aman)."""
    if not normalized_value:
        return ""
    derive = hashlib.sha256(f"identity|{settings.PII_ENCRYPTION_KEY}".encode()).digest()
    message = f"{tenant_id}|{normalized_value}".encode()
    return hmac.new(derive, message, hashlib.sha256).hexdigest()


def normalize_phone(value: str) -> str:
    """Telepon → kanonis Indonesia `+62…` (Spec §10.1 E.164 presentation)."""
    raw = (value or "").strip()
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0"):  # format lokal 08xx
        digits = "62" + digits[1:]
    elif digits.startswith("8"):  # tanpa kode negara
        digits = "62" + digits
    return "+" + digits
