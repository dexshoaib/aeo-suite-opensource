"""Sites models: client site, domains, and ownership verification status.

Hierarchy per ARCHITECTURE.md:
Agency Organization -> Client Workspace -> Site.

Tenancy per ADR-0004:
Site carries an organization ForeignKey and uses the shared TenantManager
from apps.core.tenancy, so it is scoped automatically whenever an
organization is active (request path via TenantViewSet, request-less
path via scope_to_organization).

Site also carries a workspace ForeignKey connecting it to the client
workspace container.
"""

import secrets

from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.models import Organization, Workspace
from apps.core.models import TimeStampedModel
from apps.core.tenancy import TenantManager


def generate_verification_token() -> str:
    """Generate a URL-safe cryptographic token for site verification."""
    return secrets.token_urlsafe(32)


class Site(TimeStampedModel):
    """Client site registered within a workspace and organization."""

    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending Verification"
        VERIFIED = "verified", "Verified"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="sites",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="sites",
    )
    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=255)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    verification_token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_verification_token,
        editable=False,
    )

    objects = TenantManager()

    class Meta:
        db_table = "sites_site"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "domain"],
                name="unique_workspace_domain",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.domain})"

    def clean(self) -> None:
        super().clean()
        if self.workspace_id and self.organization_id:
            if self.workspace.organization_id != self.organization_id:
                raise ValidationError("Workspace must belong to the same organization as the site.")
