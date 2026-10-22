"""Settings dasar Umrovia — env-driven, tanpa secret bawaan (Spec §18.4, §19.6)."""
import dj_database_url

from config.env import BASE_DIR, env, env_bool, env_list

VERSION = "0.1.0"  # dipakai health endpoint & User-Agent

# --- Core -------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY")  # wajib di production; local.py menyediakan fallback dev
DEBUG = env_bool("DEBUG", "False")

# `.localhost` (wildcard) = subdomain dev untuk tenant resolver S03: <slug>.localhost
ALLOWED_HOSTS = [*env_list("ALLOWED_HOSTS", "localhost,127.0.0.1"), ".localhost"]
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:3000,http://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    # Umrovia modules (Spec §2.1 modular monolith)
    "modules.identity",
    "modules.tenants",
    "modules.trial",
    "modules.travel_finance",
    "modules.audit",
    "modules.documents",
]

MIDDLEWARE = [
    "common.middleware.RequestIDMiddleware",  # T10: request ID + logging context (paling atas)
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "modules.tenants.middleware.TenantContextMiddleware",  # T06: setelah auth — resolve tenant
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ---------------------------------------------------------------
# Wajib PostgreSQL (RLS + transaksi ACID, Spec §2.1). DATABASE_URL contoh:
# postgres://user:pass@localhost:5432/umrovia
DATABASES = {
    "default": dj_database_url.config(
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=env_bool("DB_SSL_REQUIRE", "False"),
    )
}

# --- Auth -------------------------------------------------------------------
AUTH_USER_MODEL = "identity.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Cache (throttle auth S02, queryset cache; Redis bila REDIS_URL tersedia) ---
_redis_url = env("REDIS_URL")
if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "umrovia",
        }
    }

# --- API (Spec §8) ----------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth-register": "20/hour",
        "auth-login": "10/min",
        "auth-verify": "30/hour",
        "auth-resend": "10/hour",
        "auth-forgot": "5/hour",
        "anon": "60/min",
    },
    "EXCEPTION_HANDLER": "common.api.exception_handler",  # RFC7807-style (Spec §8)
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"] + (
        ["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []
    ),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Umrovia API",
    "DESCRIPTION": "SaaS manajemen travel Umroh & Haji — /api/v1 (tenant), /api/v1/portal (jamaah), "
    "/api/v1/platform (platform admin).",
    "VERSION": VERSION,
    "SERVE_INCLUDE_SCHEMA": False,
}

# --- CORS -------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
CORS_ALLOW_CREDENTIALS = True

# --- Locale -----------------------------------------------------------------
LANGUAGE_CODE = "id"
TIME_ZONE = "UTC"  # konvensi Spec §5: timestamp selalu UTC
USE_I18N = True
USE_TZ = True

# --- Static & media ---------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "backend" / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "backend" / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Email (Spec §11: event-based, via outbox di F07) ------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "25") or "25")
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", "False")
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", "False")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Umrovia <no-reply@umrovia.com>")

# --- Brand / produk (Spec §18.4) --------------------------------------------
BRAND_NAME = env("BRAND_NAME", "Umrovia")
PUBLIC_SITE_URL = env("PUBLIC_SITE_URL", "http://localhost:3001")
TENANT_APP_URL = env("TENANT_APP_URL", "http://localhost:3000")
# Basis domain tempat subdomain = slug tenant (Spec §2.2 resolver): <slug>.<base>
TENANT_DOMAIN_BASES = [b.strip().lower() for b in env("TENANT_DOMAIN_BASES", "umrovia.com,localhost").split(",") if b.strip()]
PLATFORM_ADMIN_URL = env("PLATFORM_ADMIN_URL", "http://localhost:3002")
PUBLIC_API_URL = env("PUBLIC_API_URL", "http://localhost:8000")
TRIAL_DAYS = int(env("TRIAL_DAYS", "30") or "30")
TRIAL_DUMMY_BOOKING_LIMIT = int(env("TRIAL_DUMMY_BOOKING_LIMIT", "20") or "20")  # POL-08
TRIAL_INTERNAL_USER_LIMIT = int(env("TRIAL_INTERNAL_USER_LIMIT", "3") or "3")  # POL-08

# --- Observability (T10) ----------------------------------------------------
REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "()": "common.logging.StructuredFormatter",
        },
    },
    "filters": {
        "request_id": {"()": "common.logging.RequestIDFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO"), "propagate": False},
        "modules": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO"), "propagate": False},
    },
}
