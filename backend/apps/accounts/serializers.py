"""Serializers for the accounts API (organizations and workspaces)."""

from rest_framework import serializers

from apps.accounts.models import Organization, Workspace


class OrganizationSerializer(serializers.ModelSerializer):
    """Serialize an organization; the id is the value for the selector header."""

    class Meta:
        model = Organization
        fields = ["id", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class WorkspaceSerializer(serializers.ModelSerializer):
    """Serialize a workspace; its organization is bound server-side on create."""

    organization = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Workspace
        fields = ["id", "organization", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "organization", "created_at", "updated_at"]
