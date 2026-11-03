"""Django admin registration for sites."""

from django.contrib import admin

from apps.accounts.admin import OrgScopedAdminMixin
from apps.sites.models import Site


@admin.register(Site)
class SiteAdmin(OrgScopedAdminMixin, admin.ModelAdmin):
    """Admin-side tenancy for sites: member-org rows only, full view for superusers."""

    organization_lookup = "organization__"
    list_display = (
        "name",
        "domain",
        "workspace",
        "organization",
        "verification_status",
        "created_at",
    )
    search_fields = ("name", "domain")
    list_filter = ("verification_status", "organization")
    readonly_fields = ("verification_token", "created_at", "updated_at")
