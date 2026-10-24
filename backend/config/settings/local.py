"""Settings lokal (development). Secret dev hanya dipakai saat DEBUG."""
import os

from config.settings.base import *  # noqa: F401,F403
from config.settings.base import DEBUG, SECRET_KEY  # noqa: F401

# Local default: DEBUG aktif kecuali di-set eksplisit di environment.
if "DEBUG" not in os.environ:
    DEBUG = True  # noqa: F405

if not DEBUG and not SECRET_KEY:
    raise RuntimeError("SECRET_KEY wajib di-set ketika DEBUG=False (lihat .env.example)")

if not SECRET_KEY:  # DEBUG tanpa SECRET_KEY: key hanya untuk proses lokal ini
    SECRET_KEY = "django-insecure-local-dev-only-umrovia"  # noqa: S105

if not PII_ENCRYPTION_KEY:  # noqa: F405 — dev-only: derive deterministik dari SECRET_KEY
    import base64
    import hashlib

    PII_ENCRYPTION_KEY = base64.urlsafe_b64encode(  # noqa: F405
        hashlib.sha256(f"umrovia-dev-pii|{SECRET_KEY}".encode()).digest()  # noqa: S105
    ).decode()
