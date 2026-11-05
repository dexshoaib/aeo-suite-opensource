"""Tenant-scoped API viewsets for sites.

Subclasses TenantViewSet from apps.core.tenancy: auto-registers into
TENANT_VIEWSET_REGISTRY for the structural cross-tenant leak test.
Foreign sites answer 404, never 403.
"""

import uuid

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.roles import EDITOR, user_has_org_role
from apps.core.tenancy import TenantViewSet
from apps.sites.models import Site
from apps.sites.serializers import SiteSerializer
from apps.sites.verification import verify_site


class SiteVerifyThrottle(SimpleRateThrottle):
    """Per-organization rate limit for verification runs (SPEC-1.2)."""

    scope = "site_verify"

    def get_cache_key(self, request, view):
        organization = getattr(view, "organization", None)
        if organization is None:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"org:{organization.pk}",
        }


class SiteViewSet(TenantViewSet):
    """List/CRUD for sites inside the selected organization."""

    queryset = Site.objects.all()
    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.action == "verify":
            return [SiteVerifyThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        qs = super().get_queryset()
        workspace_id = self.request.query_params.get("workspace")
        if workspace_id:
            try:
                uuid.UUID(workspace_id)
            except (ValueError, AttributeError):
                # Malformed selector behaves like an unknown one: empty
                # result, never a 500 from the UUID field conversion.
                return qs.none()
            qs = qs.filter(workspace_id=workspace_id)
        return qs

    def perform_create(self, serializer):
        # Organization comes strictly from the resolved context, never the request body
        serializer.save(organization=self.organization)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"], url_path="verify")
    def verify(self, request, *args, **kwargs):
        """Run ownership verification; 200 even when the check fails."""
        site = self.get_object()
        if not user_has_org_role(request.user, site.organization, EDITOR):
            return Response(
                {"detail": "Your role cannot run verification for this organization."},
                status=status.HTTP_403_FORBIDDEN,
            )
        verify_site(site)
        return Response(self.get_serializer(site).data)
