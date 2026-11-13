"""
Django settings for TalentFlow AI.

Multi-tenant recruitment intelligence platform using django-tenants
(schema-per-tenant). Requires PostgreSQL.
"""

import base64
import hashlib
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# Security settings for production
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() in ("true", "1", "yes")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ---------------------------------------------------------------------------
# django-tenants app split
# ---------------------------------------------------------------------------
SHARED_APPS = (
    "django_tenants",
    "tenants",
    "accounts",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    "django.contrib.staticfiles",
    "storages",
)

TENANT_APPS = (
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "portal",
    "consent",
    "recruitment",
    "profiles",
    "workforce",
    "talent",
    "notifications",
)

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.TenantAccessMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "portal.context_processors.org_profile",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database (PostgreSQL required for django-tenants)
# ---------------------------------------------------------------------------
_DB_SSLMODE = os.getenv("DB_SSLMODE", "")
DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": os.getenv("DB_NAME", "talentflow"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", "postgres"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
        # Serverless-friendly: do not keep stale connections between invocations.
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "0")),
        # Required when talking through connection poolers (Supavisor/PgBouncer).
        "DISABLE_SERVER_SIDE_CURSORS": True,
        **({"OPTIONS": {"sslmode": _DB_SSLMODE}} if _DB_SSLMODE else {}),
    }
}

DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)

# ---------------------------------------------------------------------------
# Cache (required by django-ratelimit; LocMem in dev, swap to Redis in prod)
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# ---------------------------------------------------------------------------
# django-ratelimit
# ---------------------------------------------------------------------------
RATELIMIT_USE_CACHE = "default"

TENANT_MODEL = "tenants.Client"
TENANT_DOMAIN_MODEL = "tenants.Domain"

# Schema that holds shared apps (tenants, accounts, auth, sessions, admin).
# Keep "public" for local dev; production uses a dedicated "talentflow" schema
# so the app never mixes its tables with other projects on the same Supabase DB.
PUBLIC_SCHEMA_NAME = os.getenv("PUBLIC_SCHEMA_NAME", "public")

# Demo tenant schema. Production uses a prefixed name ("tf_neepco") so every
# TalentFlow table is easy to identify in Supabase's Table Editor.
DEMO_TENANT_SCHEMA = os.getenv("DEMO_TENANT_SCHEMA", "neepco")

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "portal.backends.CandidatePortalBackend",
]

# ---------------------------------------------------------------------------
# Auth / password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# End the session when the browser is closed (session cookie, not persistent).
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# ---------------------------------------------------------------------------
# Internationalization (English + Hindi for candidate portal)
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("hi", "हिन्दी (Hindi)"),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Kolkata")

USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / media
# ---------------------------------------------------------------------------
# Absolute URL: Django's {% static %} tag returns STATIC_URL verbatim, so a
# relative value ("static/") breaks nested pages such as /portal/login/.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Supabase Storage (S3-compatible). Generate an access key pair in the
# Supabase dashboard: Storage -> S3. When these are unset, local disk is used.
SUPABASE_S3_ENDPOINT = os.getenv("SUPABASE_S3_ENDPOINT", "")
SUPABASE_S3_REGION = os.getenv("SUPABASE_S3_REGION", "ap-south-1")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "talentflow-media")
SUPABASE_S3_ACCESS_KEY = os.getenv("SUPABASE_S3_ACCESS_KEY_ID", "")
SUPABASE_S3_SECRET_KEY = os.getenv("SUPABASE_S3_SECRET_ACCESS_KEY", "")

if SUPABASE_S3_ENDPOINT and SUPABASE_S3_ACCESS_KEY and SUPABASE_S3_SECRET_KEY:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "access_key": SUPABASE_S3_ACCESS_KEY,
                "secret_key": SUPABASE_S3_SECRET_KEY,
                "bucket_name": SUPABASE_STORAGE_BUCKET,
                "endpoint_url": SUPABASE_S3_ENDPOINT,
                "region_name": SUPABASE_S3_REGION,
                "addressing_style": "path",
                "signature_version": "s3v4",
                # Private bucket: FileField.url returns a short-lived signed URL.
                "default_acl": None,
                "querystring_auth": True,
                "file_overwrite": False,
            },
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
else:
    # Local disk for development and for build-time collectstatic.
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# LLM client (pluggable — swap provider via env vars only)
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))

# ---------------------------------------------------------------------------
# DigiLocker (mock during Phase I dev)
# ---------------------------------------------------------------------------
DIGILOCKER_MOCK = os.getenv("DIGILOCKER_MOCK", "True").lower() in ("true", "1", "yes")
DIGILOCKER_API_KEY = os.getenv("DIGILOCKER_API_KEY", "")

# ---------------------------------------------------------------------------
# Aadhaar e-KYC (mock until UIDAI AUA/KUA registration is approved)
# ---------------------------------------------------------------------------
AADHAAR_MOCK = os.getenv("AADHAAR_MOCK", "True").lower() in ("true", "1", "yes")
AADHAAR_AUA_ID = os.getenv("AADHAAR_AUA_ID", "")
AADHAAR_KUA_ID = os.getenv("AADHAAR_KUA_ID", "")

# ---------------------------------------------------------------------------
# NCS / Employment Exchange feed (env-gated mock)
# ---------------------------------------------------------------------------
NCS_MOCK = os.getenv("NCS_MOCK", "True").lower() in ("true", "1", "yes")
NCS_API_BASE = os.getenv("NCS_API_BASE", "")
NCS_API_KEY = os.getenv("NCS_API_KEY", "")

# ---------------------------------------------------------------------------
# Phase 1: PII encryption (Fernet key for profiles.fields.EncryptedTextField)
# ---------------------------------------------------------------------------
_ENCRYPTION_KEY = os.getenv("DJANGO_ENCRYPTION_KEY", "")
if not _ENCRYPTION_KEY:
    # Dev fallback: derive a stable Fernet-compatible key from SECRET_KEY.
    _ENCRYPTION_KEY = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()).decode()
ENCRYPTION_KEY = _ENCRYPTION_KEY

# ---------------------------------------------------------------------------
# Phase 1: Celery / async task processing
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
# Run tasks synchronously in development (DEBUG=True) unless a broker is set up.
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", str(DEBUG)).lower() in ("true", "1", "yes")
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

# ---------------------------------------------------------------------------
# Notifications (console provider by default; swap via NOTIFY_PROVIDER env)
# ---------------------------------------------------------------------------
NOTIFY_PROVIDER = os.getenv("NOTIFY_PROVIDER", "console")
