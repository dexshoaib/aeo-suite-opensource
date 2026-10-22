"""URL configuration for the AEO Suite backend.

Route map (grows as features land): /admin/ Django admin,
/api/v1/health/ liveness + database probe, /api/v1/organizations/ and
/api/v1/workspaces/ tenant viewsets. The auth flow (/api/auth/...) and
the schema/docs endpoints (/api/schema/, /api/docs/) arrive with the
auth and schema tasks.
"""

from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import OrganizationViewSet, WorkspaceViewSet
from apps.core.views import HealthView

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="organizations")
router.register("workspaces", WorkspaceViewSet, basename="workspaces")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", HealthView.as_view(), name="health"),
    path("api/v1/", include(router.urls)),
]
