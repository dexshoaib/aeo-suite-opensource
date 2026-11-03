"""Tenant-scoped API viewsets for sites.

Subclasses TenantViewSet from apps.core.tenancy: auto-registers into
TENANT_VIEWSET_REGISTRY for the structural cross-tenant leak test.
Foreign sites answer 404, never 403.
"""

from rest_framework.permissions import IsAuthenticated

from apps.core.tenancy import TenantViewSet
from apps.sites.models import Site
from apps.sites.serializers import SiteSerializer


class SiteViewSet(TenantViewSet):
    """List/CRUD for sites inside the selected organization."""

    queryset = Site.objects.all()
    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        workspace_id = self.request.query_params.get("workspace")
        if workspace_id:
            qs = qs.filter(workspace_id=workspace_id)
        return qs

    def perform_create(self, serializer):
        # Organization comes strictly from the resolved context, never the request body
        serializer.save(organization=self.organization)
