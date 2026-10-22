"""
Development settings: DEBUG on, console email, localhost-only.

manage.py defaults to this module. Never used in CI (tests run with
config.settings.test) and never in production.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True

# Signup and verification mail prints to the runserver console.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Development auth runs behind the frontend dev server: the browser only
# ever talks to localhost:3000 and Django keeps CSRF on, trusting that
# single frontend origin. Production adds its real frontend origin at
# deploy time.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:3000"],
)
