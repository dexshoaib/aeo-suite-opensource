"""
Development settings: DEBUG on, console email, localhost-only.

manage.py defaults to this module. Never used in CI (tests run with
config.settings.test) and never in production.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True

EMAIL_BACKEND = "django.core.email.backends.console.EmailBackend"

# ADR-0005: dev auth runs behind the Next.js same-origin proxy (chunk 0.3).
# The browser only ever talks to localhost:3000; Django keeps CSRF on and
# trusts that single frontend origin. This placeholder lands in 0.2 per
# the ADR; production adds its real frontend origin at deploy time.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:3000"],
)
