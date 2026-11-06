from django.apps import AppConfig


class SitesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sites"
    label = "client_sites"
    verbose_name = "Sites"

    def ready(self) -> None:
        from apps.sites import (
            checks,  # noqa: F401
            reverification,  # noqa: F401
        )
