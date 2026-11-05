"""Serializers for the sites API."""

from urllib.parse import urlparse

from rest_framework import serializers

from apps.accounts.models import Workspace
from apps.accounts.roles import EDITOR, user_has_org_role
from apps.core.tenancy import get_current_organization
from apps.sites.models import Site, generate_verification_token


class SiteSerializer(serializers.ModelSerializer):
    """Serialize a site; organization is bound server-side from resolved context.

    verification_token is exposed only to editor-level roles and above
    (SPEC-1.2 amendment 2); other members receive an empty string so the
    generated client schema stays stable.
    """

    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    workspace = serializers.PrimaryKeyRelatedField(queryset=Workspace.objects.all())
    verification_token = serializers.SerializerMethodField()

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
            "verified_at",
            "verification_checked_at",
            "verification_error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "verification_status",
            "verification_token",
            "verified_at",
            "verification_checked_at",
            "verification_error",
            "created_at",
            "updated_at",
        ]

    def get_verification_token(self, obj: Site) -> str:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user_has_org_role(user, obj.organization, EDITOR):
            return obj.verification_token
        return ""

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
        if not domain or "." not in domain or "@" in domain:
            # "@" rejects embedded credentials (SPEC-1.2 amendment 2).
            raise serializers.ValidationError(
                "Enter a valid domain name (e.g. example.com)."
            )
        return domain

    def update(self, instance: Site, validated_data: dict) -> Site:
        """Reset verification when the domain changes (SPEC-1.2 amendment 2)."""
        domain_changed = (
            "domain" in validated_data and validated_data["domain"] != instance.domain
        )
        instance = super().update(instance, validated_data)
        if domain_changed:
            instance.verification_status = Site.VerificationStatus.PENDING
            instance.verification_token = generate_verification_token()
            instance.verified_at = None
            instance.verification_checked_at = None
            instance.verification_error = ""
            instance.save(
                update_fields=[
                    "verification_status",
                    "verification_token",
                    "verified_at",
                    "verification_checked_at",
                    "verification_error",
                    "updated_at",
                ]
            )
        return instance
