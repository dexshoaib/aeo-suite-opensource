"""
Test settings (pytest-django): fast password hasher, in-memory email.

The test database is real Postgres (test_aeo_suite), created and torn
down by pytest-django on every run. SQLite is banned (ADR-0004 rule 7).
"""

from .base import *  # noqa: F401,F403

DEBUG = False

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
