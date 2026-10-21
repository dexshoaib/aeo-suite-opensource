"""
Shared settings for the AEO Suite backend (chunk 0.2 skeleton).

Settings grow chunk by chunk: this file is the Task 2 baseline (Django +
DRF + drf-spectacular). The core/accounts apps (Tasks 3-6), allauth
headless (Task 7) and the strict schema config (Task 8) are added here as
full-file replacements in their own commits.

All environment values come from the repo-root .env via django-environ
(see .env.example). The .env file is gitignored and never committed.
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
environ.Env.read_env(BASE_DIR.parent / ".env")  # repo-root .env (0.1 convention)

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
    # Third-party (chunk 0.2)
    "rest_framework",
    "drf_spectacular",
    # Project apps (chunk 0.2, Tasks 3-6)
    "apps.core",  # Task 3: base models, tenancy primitives, health view
    "apps.accounts",  # Task 4: custom user, organizations, workspaces, memberships
]

# Custom user - MUST be set before the first migrate (SPEC-0.2 decision 2;
# retrofitting it later is the one auth change Django makes genuinely painful).
AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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

DATABASES = {
    "default": env.db(),
}

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
