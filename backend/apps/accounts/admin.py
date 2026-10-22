"""Django admin registration for accounts.

Tenant surfaces (Organization, Workspace, Membership) are scoped in the
admin exactly like everywhere else: staff users see only rows of
organizations they hold a Membership in, verified by the structural
leak test. Superusers are platform operators and keep the full view -
that is an operator capability, not a tenancy path. UserAdmin is not
org-scoped because users are global, and it deliberately excludes the
password field: editing the hash by hand would corrupt it. Passwords
change via createsuperuser / changepassword / the headless flow only.
"""

from django.contrib import admin

from apps.accounts.models import Membership, Organization, User, Workspace


class OrgScopedAdminMixin:
    """Admin-side tenancy: member-org rows only, full view for superusers.

    The membership join is the sticky filter for admin querysets - the
    request-less scope_to_organization context cannot express "all
    organizations this staff member belongs to", which is what an admin
    user needs here.
    """

    # Related lookup from the model to its organization row; empty for
    # Organization itself, "organization__" for its dependent rows.
    organization_lookup = ""

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(
            **{f"{self.organization_lookup}memberships__user": request.user}
        )


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "full_name",
        "is_active",
        "is_staff",
        "is_superuser",
        "last_login",
        "created_at",
    )
    search_fields = ("email", "full_name")
    list_filter = ("is_active", "is_staff", "is_superuser")
    readonly_fields = ("last_login", "created_at", "updated_at")
    exclude = ("password",)


@admin.register(Organization)
class OrganizationAdmin(OrgScopedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Workspace)
class WorkspaceAdmin(OrgScopedAdminMixin, admin.ModelAdmin):
    organization_lookup = "organization__"
    list_display = ("name", "organization", "created_at")
    search_fields = ("name",)
    list_filter = ("organization",)


@admin.register(Membership)
class MembershipAdmin(OrgScopedAdminMixin, admin.ModelAdmin):
    organization_lookup = "organization__"
    list_display = ("user", "organization", "role", "created_at")
    search_fields = ("user__email", "organization__name")
    list_filter = ("role", "organization")
