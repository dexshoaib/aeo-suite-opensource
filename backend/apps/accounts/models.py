"""Accounts models: custom User, Organization, Workspace, Membership.

The custom User is active from migration 0001 (SPEC-0.2 decision 2):
AUTH_USER_MODEL is set in config/settings/base.py before the first
migrate. No auth data migrations will ever be authored for this app.

Tenancy per ADR-0004: Organization is the tenant ROOT (plain manager -
it is not itself tenant-scoped). Workspace and Membership rows carry an
organization ForeignKey and use the shared TenantManager from
apps.core.tenancy, so they are scoped automatically whenever an
organization is active (request path via TenantViewSet, request-less
path via scope_to_organization).

Roles (plan Open Question 2, default stood): minimum set owner + member;
agency/agent roles come later. The server-side Membership - never any
client header - is the authority for organization access (ADR-0004
rule 3).
"""

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from apps.accounts.managers import UserManager
from apps.core.models import TimeStampedModel
from apps.core.tenancy import TenantManager


class User(TimeStampedModel, AbstractBaseUser, PermissionsMixin):
    """Email-login user; allauth headless (Task 7) authenticates against it.

    TimeStampedModel comes first in the MRO so the UUID primary key wins
    over AbstractBaseUser's implicit auto pk.
    """

    email = models.EmailField("email address", unique=True)
    full_name = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    EMAIL_FIELD = "email"

    class Meta:
        ordering = ["email"]
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return self.email


class Organization(TimeStampedModel):
    """Tenant root. Every tenant-scoped row hangs off an organization."""

    name = models.CharField(max_length=255)

    # Explicit: Organization is the tenant itself, NOT tenant-scoped.
    objects = models.Manager()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Workspace(TimeStampedModel):
    """Tenant-scoped container inside an organization (sites land in 1.x)."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="workspaces"
    )
    name = models.CharField(max_length=255)

    objects = TenantManager()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.organization} / {self.name}"


class Membership(TimeStampedModel):
    """User <-> Organization link; the server-side authority for org access."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MEMBER = "member", "Member"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.MEMBER)

    objects = TenantManager()

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="unique_membership_per_org",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.role})"
