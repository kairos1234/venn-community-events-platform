"""Django settings.

Deliberately minimal: there are no users, sessions or admin site (the brief only needs
demo roles), so django.contrib.auth/sessions/admin and CSRF middleware are left out.
Everything is configurable through environment variables and has a working default.
"""

import os
from pathlib import Path

from django.core.management.utils import get_random_secret_key
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


def env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes")


# Nothing is signed or stored in sessions, so a fresh random key per process is fine and
# means there is no secret to commit. Set DJANGO_SECRET_KEY if you ever need a stable one.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or get_random_secret_key()

# Off by default so error responses never include debug pages, settings or stack traces.
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"] + [
    host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if host.strip()
]

INSTALLED_APPS = [
    "backend.events",
    "backend.registrations",
    "backend.notifications",
    "backend.api",
]

MIDDLEWARE = [
    "backend.api.middleware.RequestContextMiddleware",  # request ID + request logging (outermost)
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"
WSGI_APPLICATION = "backend.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("EVENTS_DB_PATH", BASE_DIR / "db.sqlite3"),
        "OPTIONS": {
            # Take SQLite's write lock when a transaction starts. This makes
            # "check capacity, then insert the registration" safe against a concurrent writer.
            "transaction_mode": "IMMEDIATE",
            "timeout": 10,
        },
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True
TIME_ZONE = "UTC"

# The frontend only loads same-origin scripts and styles and renders event text as plain text.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:"],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.NONE],
    "frame-ancestors": [CSP.NONE],
}

# Event requests are tiny; refuse anything larger than 64 KB.
DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "app": {
            "()": "backend.request_context.RequestIdFormatter",
            "format": "%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "app", "stream": "ext://sys.stdout"},
    },
    "loggers": {
        "backend": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # runserver's own access log would duplicate the request log (which has request IDs).
        "django.server": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
