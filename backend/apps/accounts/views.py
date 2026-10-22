"""Tenant-scoped API viewsets for organizations and workspaces.

Both viewsets ride the shared TenantViewSet base: the organization is
resolved per request through the membership-checked selector header
(apps.accounts.org_context), activated for the auto-scoping manager, and
reset when the response is finalized. Foreign rows answer 404, never
403.
"""

from django.db import transaction
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import Membership, Organization, Workspace
from apps.accounts.serializers import OrganizationSerializer, WorkspaceSerializer
from apps.core.tenancy import TenantViewSet


class OrganizationViewSet(TenantViewSet):
    """List/CRUD for organizations the authenticated user belongs to.

    List shows member organizations only (server-side membership join).
    Creating an organization makes the creator its owner by writing the
    founding Membership row in the same transaction as the organization.
    """

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Organization is the tenant root, not itself tenant-scoped: the
        # membership join replaces the sticky org filter of the base.
        return Organization.objects.filter(memberships__user=self.request.user)

    @transaction.atomic
    def perform_create(self, serializer):
        organization = serializer.save()
        Membership.objects.create(
            organization=organization,
            user=self.request.user,
            role=Membership.Role.OWNER,
        )


class WorkspaceViewSet(TenantViewSet):
    """List/CRUD for workspaces inside the selected organization.

    The selector header picks the organization; the base queryset filter
    plus the auto-scoping manager keep foreign workspaces invisible (404
    on retrieve). Without a selector the list is simply empty.
    """

    queryset = Workspace.objects.all()
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # Organization comes from the resolved context, never the request
        # body - a client cannot choose another organization here.
        serializer.save(organization=self.organization)
