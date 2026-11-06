"""
Django settings for the Malam Nasiru Bala Ja'oji Youths Network (MNBJYN) website.

Configuration is driven by environment variables so the same code runs
locally and in production:

    DJANGO_SECRET_KEY      long random string (REQUIRED when DEBUG is off)
    DJANGO_DEBUG           "1" (default) or "0"
    DJANGO_ALLOWED_HOSTS   comma-separated hostnames for the deployed site
    DJANGO_CSRF_ORIGINS    comma-separated origins, e.g. "https://ssbyn.org"
"""
import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# True when running on Vercel (Vercel sets VERCEL=1 automatically).
ON_VERCEL = bool(os.environ.get("VERCEL"))

# Debug is ON locally by default and OFF on Vercel by default.
DEBUG = os.environ.get("DJANGO_DEBUG", "0" if ON_VERCEL else "1") == "1"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
SECRET_KEY_IS_FALLBACK = not SECRET_KEY   # reported by the go-live checks
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-change-me"
    elif ON_VERCEL:
        # Keeps the site booting before you add DJANGO_SECRET_KEY in the Vercel
        # dashboard. SET DJANGO_SECRET_KEY before using the admin for real.
        SECRET_KEY = "vercel-fallback-" + os.environ.get("VERCEL_PROJECT_ID", "mnbjyn")
    else:
        raise RuntimeError("Set DJANGO_SECRET_KEY when DJANGO_DEBUG=0")

_default_hosts = "localhost,127.0.0.1"
if ON_VERCEL:
    _default_hosts += ",.vercel.app"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", _default_hosts).split(",")
    if h.strip()
]
# Always allow the deployment's own Vercel hostnames.
for _var in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
    _host = os.environ.get(_var)
    if _host and _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("DJANGO_CSRF_ORIGINS", "").split(",") if o.strip()
]
if ON_VERCEL:
    CSRF_TRUSTED_ORIGINS.append("https://*.vercel.app")
    for _var in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        _host = os.environ.get(_var)
        if _host:
            CSRF_TRUSTED_ORIGINS.append(f"https://{_host}")

# Keep the login in a signed cookie so it works across serverless instances
# (otherwise saving in /admin can log you out when the next request lands on
# a different server that has its own empty temporary database).
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14

INSTALLED_APPS = [
    # "core" comes first so its admin template overrides are picked up.
    "core",
    "core.admin_apps.SSBYNAdminConfig",  # replaces django.contrib.admin
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.api.middleware.ApiMiddleware",          # CORS + headers for /api/
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.NoStoreHTMLMiddleware",
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
                "core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database: set DATABASE_URL (e.g. a Neon / Supabase / Vercel Postgres URL) for
# permanent storage. Without it we use SQLite: next to the code locally, or in
# /tmp on Vercel (read-only filesystem elsewhere) -- which is TEMPORARY storage
# that resets, so use Postgres for real member registrations.
_sqlite_path = "/tmp/db.sqlite3" if ON_VERCEL else BASE_DIR / "db.sqlite3"
DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        default=f"sqlite:///{_sqlite_path}",
        conn_max_age=0 if ON_VERCEL else 600,
        ssl_require=False,
    )
}

USING_SQLITE = DATABASES["default"]["ENGINE"].endswith("sqlite3")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Serve app static files directly (no collectstatic step needed on Vercel).
WHITENOISE_USE_FINDERS = True
STORAGES = {
    # Uploaded photos live in the database so they survive on Vercel.
    "default": {"BACKEND": "core.storage.DatabaseStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_CONTENT_TYPE_NOSNIFF = True


# ---------------------------------------------------------------------------
# Results API (/api/v1/) - see docs/API.md
# ---------------------------------------------------------------------------
def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# How long an app login stays valid (hours). Election day is long: default 3 days.
API_TOKEN_TTL_HOURS = _env_int("API_TOKEN_TTL_HOURS", 72)
# Lock an agent's login after this many wrong PINs, for this many minutes.
API_LOGIN_MAX_FAILS = _env_int("API_LOGIN_MAX_FAILS", 5)
API_LOGIN_LOCK_MINUTES = _env_int("API_LOGIN_LOCK_MINUTES", 15)
# Browser origins (not mobile apps) allowed to call the private endpoints, e.g.
# "https://agents.example.org". Public read-only endpoints are open to everyone.
API_CORS_ORIGINS = [
    o.strip() for o in os.environ.get("API_CORS_ORIGINS", "").split(",") if o.strip()
]
# Trust X-Forwarded-For for rate limiting / audit IPs (true behind Vercel or another proxy).
API_TRUST_PROXY = os.environ.get("API_TRUST_PROXY", "1" if ON_VERCEL else "0") == "1"
API_MAX_JSON_BYTES = 1_000_000
# Vercel rejects request bodies above 4.5 MB, so sheet photos are capped below that.
API_MAX_SHEET_BYTES = _env_int("API_MAX_SHEET_BYTES", 4_000_000)
