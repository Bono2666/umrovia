"""Settings production — gagal cepat bila konfigurasi tidak aman (Spec §13, §18.2)."""
from config.env import env, env_bool, env_list  # noqa: F401
from config.settings.base import *  # noqa: F401,F403

SECRET_KEY = env("SECRET_KEY", required=True)  # noqa: F405
DEBUG = False  # noqa: F405

# Enkripsi NIK/paspor jamaah (Spec §5.2): key eksplisit, tanpa fallback (§18.4).
if not PII_ENCRYPTION_KEY:  # noqa: F405
    raise RuntimeError("PII_ENCRYPTION_KEY wajib di-set di production (lihat .env.example)")

if not env_bool("ALLOW_INSECURE", "False"):
    # TLS wajib di belakang reverse proxy (Spec §18.2)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", "True")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "0") or "0")  # staged rollout dulu 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    # Header HSTS untuk semua host dikirim Caddy (infra/deploy/Caddyfile); Django tetap sama untuk API.
    # Preload praktis tak bisa dibatalkan cepat → hanya dengan keputusan tertulis (DEPLOY_ROLLBACK.md).
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", "False")

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# Host-only cookie per Spec §18.2 — set domain eksplisit hanya bila memang dibutuhkan.
SESSION_COOKIE_DOMAIN = env("SESSION_COOKIE_DOMAIN", None)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")  # noqa: F405
if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["localhost", "127.0.0.1"]:
    raise RuntimeError("ALLOWED_HOSTS production harus diisi eksplisit (bukan default lokal)")
