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
