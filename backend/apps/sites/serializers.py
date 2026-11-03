"""Serializers for the sites API."""

from urllib.parse import urlparse

from rest_framework import serializers

from apps.accounts.models import Workspace
from apps.core.tenancy import get_current_organization
from apps.sites.models import Site


class SiteSerializer(serializers.ModelSerializer):
    """Serialize a site; organization is bound server-side from resolved context."""

    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    workspace = serializers.PrimaryKeyRelatedField(queryset=Workspace.objects.all())

    class Meta:
        model = Site
        fields = [
            "id",
            "organization",
            "workspace",
            "name",
            "domain",
            "verification_status",
            "verification_token",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "verification_status",
            "verification_token",
            "created_at",
            "updated_at",
        ]

    def validate_workspace(self, value: Workspace) -> Workspace:
        """Validate that workspace belongs to the requesting user's active organization,

        and enforce immutability on update.
        """
        active_org = get_current_organization()
        if active_org is not None and value.organization_id != active_org.id:
            raise serializers.ValidationError(
                "Workspace does not belong to the selected organization."
            )
        if self.instance is not None and self.instance.workspace_id != value.id:
            raise serializers.ValidationError(
                "Moving a site between workspaces is not supported."
            )
        return value

    def validate_domain(self, value: str) -> str:
        """Normalize domain string: lowercase, strip protocol, paths, and trailing slashes."""
        raw = value.strip().lower()
        if raw.startswith("http://") or raw.startswith("https://"):
            parsed = urlparse(raw)
            domain = parsed.netloc or parsed.path
        else:
            domain = raw.split("/")[0].split("?")[0].split("#")[0]

        domain = domain.split(":")[0].strip()
        if not domain or "." not in domain:
            raise serializers.ValidationError(
                "Enter a valid domain name (e.g. example.com)."
            )
        return domain
