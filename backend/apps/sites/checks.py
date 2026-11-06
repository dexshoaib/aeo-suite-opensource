from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, register


@register()
def check_reverification_settings(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    """Validate that site re-verification configuration settings are positive integers."""
    errors: list[CheckMessage] = []
    settings_to_check = [
        ("SITE_REVERIFICATION_INTERVAL_DAYS", "sites.E001"),
        ("SITE_REVERIFICATION_PER_ORG_LIMIT", "sites.E002"),
        ("SITE_REVERIFICATION_MAX_PER_SWEEP", "sites.E003"),
    ]
    for setting_name, error_id in settings_to_check:
        val = getattr(settings, setting_name, None)
        if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
            errors.append(
                Error(
                    f"{setting_name} must be a positive integer (got {val!r}).",
                    id=error_id,
                )
            )
    return errors
