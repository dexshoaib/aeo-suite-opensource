"""
Shared settings for the AEO Suite backend.

Settings grow feature by feature as full-file replacements in their own
commits: this baseline carries Django core, DRF (session auth +
drf-spectacular schema), cookie-session auth via django-allauth in
headless mode, and the project apps. All environment values come from
the repo-root .env via django-environ (see .env.example). The .env file
is gitignored and never committed.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/

env = environ.Env(
    DJANGO_SECRET_KEY=(str, "insecure-dev-only-key-not-for-production"),
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DATABASE_URL=(str, "postgres://postgres:postgres@localhost:5432/aeo_suite"),
)
environ.Env.read_env(BASE_DIR.parent / ".env")  # repo-root .env

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third-party
    "rest_framework",
    "drf_spectacular",
    "allauth",
    "allauth.account",
    "allauth.headless",
    # Project apps
    "apps.core",  # base models, tenancy primitives, health view
    "apps.accounts",  # custom user, organizations, workspaces, memberships
]

# Custom user - MUST be set before the first migrate; retrofitting it
# later is the one auth change Django makes genuinely painful.
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
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

DATABASES = {
    "default": env.db(),
}

REST_FRAMEWORK = {
    # Cookie sessions are the auth mechanism for browser clients; the
    # JSON auth endpoints under /api/auth/ issue and refresh them.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # drf-spectacular's AutoSchema drives all schema generation; DRF's
    # built-in default is incompatible with it.
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# Strict schema serving: warnings fail the build because the frontend's
# TypeScript client is generated from this schema.
SPECTACULAR_SETTINGS = {
    "TITLE": "AEO Suite API",
    "VERSION": "0.1.0",
    # The schema endpoint should not document itself.
    "SERVE_INCLUDE_SCHEMA": False,
    # Browsing stays possible even once strict default permissions
    # land later.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}

# Cookie-session auth, JSON only: the headless endpoints under
# /api/auth/ are the single auth surface (no server-rendered auth pages).
SITE_ID = 1
HEADLESS_ONLY = True
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# Confirmation mail prints to the console in development and login is
# not blocked on verification; real email delivery is pre-launch
# hardening.
ACCOUNT_EMAIL_VERIFICATION = "optional"
# allauth publishes its own OpenAPI spec for the auth endpoints at
# /api/auth/openapi.{yaml,json} — kept separate from the DRF schema.
HEADLESS_SERVE_SPECIFICATION = True

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
