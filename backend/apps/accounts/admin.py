"""Django admin registration for accounts (Task 4 baseline).

Tenant-scoped admin queryset hardening (scope_to_organization /
for_organization) lands with the org-context work (Tasks 5-6) and is
verified by the structural leak test (Task 9).

UserAdmin deliberately excludes the password field: editing the hash by
hand would corrupt it. Passwords change via createsuperuser /
changepassword / the allauth headless flow (Task 7) only.
"""

from django.contrib import admin

from apps.accounts.models import Membership, Organization, User, Workspace


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
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "created_at")
    search_fields = ("name",)
    list_filter = ("organization",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "created_at")
    search_fields = ("user__email", "organization__name")
    list_filter = ("role", "organization")
